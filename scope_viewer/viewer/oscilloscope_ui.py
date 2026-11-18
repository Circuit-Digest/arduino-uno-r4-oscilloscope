"""
oscilloscope_ui.py — scope_viewer v3
──────────────────────────────────────
Clean & Modern Desktop Oscilloscope UI for Arduino UNO R4:
  • Modern Slate/Navy Theme (Clean, high-contrast, non-green)
  • Electric Cyan live trace & Warm Amber frozen hold trace
  • Smooth demo waveform animation when disconnected
  • MP4 Video Recording (native .mp4 output via OpenCV)
  • Crystal-clear PNG Screenshot capture
  • Real-time V/Div & T/Div controls synced with Arduino
  • 6-Metric measurement display (Frequency, Vpp, Vrms, V/Div, T/Div, State)
  • Serial auto-detect & background reader integration
"""

import math
import os
import queue
import time
import tkinter as tk
from datetime import datetime
from tkinter import ttk
from typing import Optional

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from serial_reader import SerialReader, list_serial_ports


# ══════════════════════════════════════════════════════════════════════════════
# ADC CALIBRATION (matches Oscilloscope.ino)
# ══════════════════════════════════════════════════════════════════════════════

ADC_VREF      = 5.0
DIVIDER_RATIO = 0.4
ADC_TO_VIN    = ADC_VREF / 1023.0 / DIVIDER_RATIO   # Volts per 10-bit count


# ══════════════════════════════════════════════════════════════════════════════
# CANVAS / DISPLAY GEOMETRY
# ══════════════════════════════════════════════════════════════════════════

DIVS_X   = 10        # horizontal divisions
DIVS_Y   = 8         # vertical divisions

CANVAS_W = 920       # canvas widget total width  (px)
CANVAS_H = 460       # canvas widget total height (px)
WAVE_X   = 60        # left edge of waveform area (margin for Y-axis voltage labels)
WAVE_Y   = 18        # top edge of waveform area
WAVE_W   = CANVAS_W - WAVE_X - 16   # waveform width
WAVE_H   = CANVAS_H - WAVE_Y - 32   # waveform height

REC_GEOM = (WAVE_X, WAVE_Y, WAVE_W, WAVE_H)   # fixed geometry for PNG/MP4 output

POLL_MS  = 50        # UI poll interval → ~20 FPS for silky-smooth display & recording


# ══════════════════════════════════════════════════════════════════════════
# MODERN CLEAN COLOUR PALETTE (Non-green, high-contrast, simple to read)
# ══════════════════════════════════════════════════════════════════════════

C_APP_BG       = "#0f172a"      # Deep slate background
C_PANEL_BG     = "#1e293b"      # Card / panel background
C_CARD_BG      = "#182234"      # Metric card background
C_CARD_BORDER  = "#2a374f"      # Card outline
C_SEP          = "#243044"      # Subtle separator lines

C_CANVAS_BG    = "#080d1a"      # Oscilloscope screen (deep midnight)
C_BORDER       = "#2a374f"      # Scope border
C_GRID         = "#162032"      # Grid division lines
C_GRID_CTR     = "#26354e"      # Center crosshair axis
C_GRID_TICK    = "#3b4f73"      # Tick marks on center axis

# Waveform Traces
C_WAVE         = "#00e5ff"      # Electric Cyan — crisp, clear live trace
C_WAVE_GLOW    = "#034e63"      # Subtle cyan glow halo
C_WAVE_FREEZE  = "#fbbf24"      # Warm Amber — frozen hold
C_WAVE_FRZ_GL  = "#5c3e03"      # Amber glow
C_WAVE_DEMO    = "#38bdf8"      # Sky Blue — demo wave
C_WAVE_DEM_GL  = "#0c4061"      # Demo glow

# Typography & Readout Colours
C_TEXT_MAIN    = "#f8fafc"      # Pure clean white
C_TEXT_MUTED   = "#94a3b8"      # Slate grey (secondary/units)
C_TEXT_DIM     = "#64748b"      # Dim annotations
C_TEXT_CYAN    = "#38bdf8"      # Cyan accent for primary values

# Status & Actions
C_CONN         = "#10b981"      # Emerald green indicator
C_DISCONN      = "#ef4444"      # Red indicator
C_REC_DOT      = "#f43f5e"      # Rose red for recording badge

# Buttons
C_BTN_CONN     = "#2563eb"      # Blue connect button
C_BTN_DISC     = "#dc2626"      # Red disconnect button
C_BTN_FREEZE   = "#d97706"      # Amber freeze button
C_BTN_RESUME   = "#4f46e5"      # Indigo resume button
C_BTN_SHOT     = "#334155"      # Slate screenshot button
C_BTN_REC      = "#be123c"      # Rose record button
C_BTN_STOP     = "#881337"      # Dark crimson stop button
C_BTN_STEP     = "#2a3447"      # Adjustment step button


# ══════════════════════════════════════════════════════════════════════════
# FONTS
# ══════════════════════════════════════════════════════════════════════════

F_TITLE    = ("Segoe UI", 12, "bold")
F_SUB      = ("Segoe UI", 9)
F_LBL      = ("Segoe UI", 9)
F_LBL_B    = ("Segoe UI", 9, "bold")
F_MK       = ("Segoe UI", 8, "bold")
F_MV       = ("Consolas", 14, "bold")
F_AX       = ("Consolas", 8)
F_BTN      = ("Segoe UI", 9, "bold")
F_BTN_SM   = ("Segoe UI", 8, "bold")
F_STATUS   = ("Segoe UI", 9)


# ══════════════════════════════════════════════════════════════════════════
# OSCILLOSCOPE APP CLASS
# ══════════════════════════════════════════════════════════════════════════

class OscilloscopeApp:
    """Modern Desktop Oscilloscope Viewer with MP4 Video Recording."""

    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("Scope Viewer · Arduino UNO R4 Oscilloscope")
        self.root.configure(bg=C_APP_BG)
        self.root.state("zoomed")                     # start maximized
        self.root.bind("<F11>", self._toggle_fullscreen)
        self.root.bind("<Escape>", lambda e: self.root.attributes("-fullscreen", False))

        # On-screen waveform geometry (x, y, w, h) — resized with the canvas.
        # Recording/screenshots always use the fixed WAVE_* constants.
        self._g: tuple[float, float, float, float] = (WAVE_X, WAVE_Y, WAVE_W, WAVE_H)
        self._cw, self._ch = CANVAS_W, CANVAS_H

        # ── State ─────────────────────────────────────────────────────────────
        self._queue: queue.Queue               = queue.Queue(maxsize=64)
        self._reader: Optional[SerialReader]   = None
        self._frozen: bool                     = False
        self._connected: bool                  = False
        self._wave_data: Optional[list[int]]   = None
        self._meta: dict                       = {
            "vdiv": "2.0",
            "tdiv": "2000",
            "freq": "1000",
            "vpp":  "5.000",
            "vrms": "1.768",
            "state": "IDLE",
        }

        # Polling
        self._poll_id: Optional[str]           = None

        # Demo animation
        self._demo_phase: float                = 0.0

        # MP4 Video Recording
        self._recording: bool                  = False
        self._video_writer: Optional[cv2.VideoWriter] = None
        self._record_path: str                 = ""
        self._record_start_time: float         = 0.0
        self._record_frames: int               = 0
        self._blink_on: bool                   = False
        self._last_frame_bgr: Optional[np.ndarray] = None

        # Load fonts for PIL video frame generator
        self._pil_font_small = self._load_pil_font(11)
        self._pil_font_large = self._load_pil_font(13)

        # ── Setup ─────────────────────────────────────────────────────────────
        self._style_ttk()
        self._build_ui()
        self._draw_grid()
        self._start_demo()

    @staticmethod
    def _load_pil_font(size: int) -> ImageFont.ImageFont:
        """Load clean TrueType font or fallback."""
        for font_name in ("consola.ttf", "arial.ttf", "segoeui.ttf"):
            try:
                return ImageFont.truetype(font_name, size)
            except Exception:
                continue
        return ImageFont.load_default()

    # ══════════════════════════════════════════════════════════════════════════
    # TTK STYLING
    # ══════════════════════════════════════════════════════════════════════════

    def _style_ttk(self) -> None:
        s = ttk.Style(self.root)
        s.theme_use("clam")
        s.configure(
            "Clean.TCombobox",
            fieldbackground="#243044",
            background="#243044",
            foreground=C_TEXT_MAIN,
            selectbackground="#334155",
            selectforeground=C_TEXT_MAIN,
            bordercolor=C_CARD_BORDER,
            arrowcolor=C_TEXT_MUTED,
            padding=4,
        )
        s.map(
            "Clean.TCombobox",
            fieldbackground=[("readonly", "#243044")],
            foreground=[("readonly", C_TEXT_MAIN)],
        )

    # ══════════════════════════════════════════════════════════════════════════
    # UI CONSTRUCTION
    # ══════════════════════════════════════════════════════════════════════════

    def _sep(self, height: int = 1) -> None:
        tk.Frame(self.root, bg=C_SEP, height=height).pack(fill=tk.X)

    def _build_ui(self) -> None:
        self._build_titlebar()
        self._sep()
        self._build_conn_toolbar()
        self._sep()
        self._build_action_toolbar()
        self._sep()
        self._build_canvas_area()
        self._sep()
        self._build_adjustment_strip()
        self._sep()
        self._build_metrics_strip()
        self._sep()
        self._build_statusbar()

    # ── Header ────────────────────────────────────────────────────────────────

    def _build_titlebar(self) -> None:
        bar = tk.Frame(self.root, bg=C_PANEL_BG, pady=9, padx=14)
        bar.pack(fill=tk.X)

        tk.Label(
            bar, text="SCOPE VIEWER",
            font=F_TITLE, fg=C_TEXT_MAIN, bg=C_PANEL_BG,
        ).pack(side=tk.LEFT)

        tk.Label(
            bar, text=" Arduino UNO R4 · Digital Oscilloscope",
            font=F_SUB, fg=C_TEXT_MUTED, bg=C_PANEL_BG,
        ).pack(side=tk.LEFT, padx=4)

        self._conn_dot = tk.Label(
            bar, text="● DISCONNECTED",
            font=F_LBL_B, fg=C_DISCONN, bg=C_PANEL_BG,
        )
        self._conn_dot.pack(side=tk.RIGHT)

    # ── Connection Toolbar ────────────────────────────────────────────────────

    def _build_conn_toolbar(self) -> None:
        bar = tk.Frame(self.root, bg=C_APP_BG, pady=8, padx=14)
        bar.pack(fill=tk.X)

        def lbl(text: str) -> None:
            tk.Label(
                bar, text=text, font=F_LBL_B,
                fg=C_TEXT_MUTED, bg=C_APP_BG,
            ).pack(side=tk.LEFT, padx=(0, 5))

        lbl("PORT:")
        self._port_var = tk.StringVar()
        self._port_cb  = ttk.Combobox(
            bar, textvariable=self._port_var,
            width=11, state="readonly", style="Clean.TCombobox",
        )
        self._port_cb.pack(side=tk.LEFT, padx=(0, 4))

        tk.Button(
            bar, text="⟳", font=("Segoe UI", 11, "bold"),
            fg=C_TEXT_MAIN, bg="#334155", activebackground="#475569",
            activeforeground=C_TEXT_MAIN, bd=0, padx=8, pady=2,
            cursor="hand2", relief=tk.FLAT,
            command=self._refresh_ports,
        ).pack(side=tk.LEFT, padx=(0, 14))

        lbl("BAUD:")
        self._baud_var = tk.StringVar(value="115200")
        ttk.Combobox(
            bar, textvariable=self._baud_var,
            values=["9600", "57600", "115200"],
            width=8, state="readonly", style="Clean.TCombobox",
        ).pack(side=tk.LEFT, padx=(0, 14))

        self._conn_btn = tk.Button(
            bar, text="⚡ CONNECT",
            font=F_BTN, fg=C_TEXT_MAIN, bg=C_BTN_CONN,
            activebackground="#1d4ed8", activeforeground=C_TEXT_MAIN,
            bd=0, padx=14, pady=5, cursor="hand2", relief=tk.FLAT,
            command=self._toggle_connection,
        )
        self._conn_btn.pack(side=tk.LEFT)

        self._conn_msg = tk.Label(
            bar, text="Ready to connect",
            font=F_LBL, fg=C_TEXT_MUTED, bg=C_APP_BG,
        )
        self._conn_msg.pack(side=tk.LEFT, padx=14)

        self._refresh_ports()

    # ── Action Toolbar ────────────────────────────────────────────────────────

    def _build_action_toolbar(self) -> None:
        bar = tk.Frame(self.root, bg=C_PANEL_BG, pady=8, padx=14)
        bar.pack(fill=tk.X)

        def btn(text: str, fg: str, bg: str, cmd, state=tk.NORMAL) -> tk.Button:
            b = tk.Button(
                bar, text=text, font=F_BTN,
                fg=fg, bg=bg, bd=0, padx=13, pady=5,
                cursor="hand2", relief=tk.FLAT, state=state,
                activebackground=bg, activeforeground=fg,
                command=cmd,
            )
            b.pack(side=tk.LEFT, padx=(0, 8))
            return b

        # Freeze / Hold
        self._freeze_btn = btn(
            "❄  FREEZE", C_TEXT_MAIN, "#475569",
            self._toggle_freeze, state=tk.DISABLED,
        )

        # Divider
        tk.Frame(bar, bg=C_SEP, width=1, height=24).pack(side=tk.LEFT, padx=6)

        # Screenshot (PNG)
        self._shot_btn = btn(
            "📷  SCREENSHOT", C_TEXT_MAIN, C_BTN_SHOT,
            self._take_screenshot,
        )

        # Record MP4 Video
        self._rec_btn = btn(
            "⏺  RECORD MP4", C_TEXT_MAIN, C_BTN_REC,
            self._toggle_record, state=tk.NORMAL,
        )

        # Live REC indicator & timer badge
        self._rec_badge = tk.Label(
            bar, text="",
            font=F_LBL_B, fg=C_REC_DOT, bg=C_PANEL_BG,
        )
        self._rec_badge.pack(side=tk.LEFT, padx=6)

    # ── Oscilloscope Canvas ───────────────────────────────────────────────────

    def _build_canvas_area(self) -> None:
        wrapper = tk.Frame(self.root, bg=C_APP_BG, padx=10, pady=8)
        wrapper.pack(fill=tk.BOTH, expand=True)

        self._canvas = tk.Canvas(
            wrapper,
            width=CANVAS_W, height=CANVAS_H,
            bg=C_CANVAS_BG,
            highlightbackground=C_BORDER,
            highlightthickness=1,
            cursor="crosshair",
        )
        self._canvas.pack(fill=tk.BOTH, expand=True)
        self._canvas.bind("<Configure>", self._on_canvas_resize)

    # ── Scale Adjustments ─────────────────────────────────────────────────────

    def _build_adjustment_strip(self) -> None:
        bar = tk.Frame(self.root, bg=C_PANEL_BG, pady=7, padx=14)
        bar.pack(fill=tk.X)

        def step_btn(parent, text, cmd):
            return tk.Button(
                parent, text=text,
                font=F_BTN_SM, fg=C_TEXT_MAIN, bg=C_BTN_STEP,
                activebackground="#3b4760", activeforeground=C_TEXT_MAIN,
                bd=0, padx=9, pady=3, cursor="hand2", relief=tk.FLAT,
                command=cmd,
            )

        def ctrl_group(label_text, default_val, dn_cmd, up_cmd):
            frame = tk.Frame(bar, bg=C_PANEL_BG)
            frame.pack(side=tk.LEFT, padx=(0, 20))
            tk.Label(
                frame, text=label_text, font=F_MK,
                fg=C_TEXT_MUTED, bg=C_PANEL_BG,
            ).pack(side=tk.LEFT, padx=(0, 6))

            step_btn(frame, "▼", dn_cmd).pack(side=tk.LEFT)
            val_lbl = tk.Label(
                frame, text=default_val, font=F_LBL_B,
                fg=C_TEXT_CYAN, bg=C_CARD_BG, width=8, padx=4, pady=2,
            )
            val_lbl.pack(side=tk.LEFT, padx=4)
            step_btn(frame, "▲", up_cmd).pack(side=tk.LEFT)
            return val_lbl

        self._vdiv_lbl = ctrl_group("VOLTS / DIV:", "2.0 V", self._vdiv_dn, self._vdiv_up)
        self._tdiv_lbl = ctrl_group("TIME / DIV:",  "2 ms",  self._tdiv_dn, self._tdiv_up)

        # Channel Indicator Badge
        ch_badge = tk.Frame(bar, bg="#0e2a38", padx=8, pady=3)
        ch_badge.pack(side=tk.RIGHT)
        tk.Label(
            ch_badge, text="CH1 · Analog In (A0)",
            font=F_LBL_B, fg=C_WAVE, bg="#0e2a38",
        ).pack()

    # ── Metrics Strip ─────────────────────────────────────────────────────────

    def _build_metrics_strip(self) -> None:
        bar = tk.Frame(self.root, bg=C_APP_BG, pady=8, padx=10)
        bar.pack(fill=tk.X)

        fields = [
            ("freq",  "FREQUENCY"),
            ("vpp",   "PEAK-TO-PEAK (Vpp)"),
            ("vrms",  "RMS VOLTAGE (Vrms)"),
            ("vdiv",  "V / DIV"),
            ("tdiv",  "T / DIV"),
            ("state", "ACQUISITION"),
        ]

        self._mvals: dict[str, tk.Label] = {}

        for key, title in fields:
            card = tk.Frame(
                bar, bg=C_CARD_BG,
                highlightbackground=C_CARD_BORDER,
                highlightthickness=1,
            )
            card.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=4)

            tk.Label(
                card, text=title, font=F_MK,
                fg=C_TEXT_MUTED, bg=C_CARD_BG, pady=4,
            ).pack()

            val = tk.Label(
                card, text="---", font=F_MV,
                fg=C_TEXT_MAIN, bg=C_CARD_BG, width=10, pady=5,
            )
            val.pack()
            self._mvals[key] = val

    # ── Status Bar ────────────────────────────────────────────────────────────

    def _build_statusbar(self) -> None:
        bar = tk.Frame(self.root, bg=C_PANEL_BG, pady=5, padx=14)
        bar.pack(fill=tk.X)

        self._status_lbl = tk.Label(
            bar, text="Ready · Demo mode active",
            font=F_STATUS, fg=C_TEXT_MUTED, bg=C_PANEL_BG, anchor=tk.W,
        )
        self._status_lbl.pack(side=tk.LEFT)

        tk.Label(
            bar, text="10-bit ADC · 115200 Baud · MP4 Recording",
            font=F_STATUS, fg=C_TEXT_DIM, bg=C_PANEL_BG,
        ).pack(side=tk.RIGHT)

    # ══════════════════════════════════════════════════════════════════════════
    # OSCILLOSCOPE GRID & LABELS
    # ══════════════════════════════════════════════════════════════════════════

    def _on_canvas_resize(self, event: tk.Event) -> None:
        self._cw, self._ch = event.width, event.height
        self._g = (WAVE_X, WAVE_Y, max(100, event.width - WAVE_X - 16), max(80, event.height - WAVE_Y - 32))
        self._draw_grid()
        if self._connected and self._wave_data:
            self._render_wave(
                self._samples_to_points(self._wave_data),
                *((C_WAVE_FREEZE, C_WAVE_FRZ_GL) if self._frozen else (C_WAVE, C_WAVE_GLOW)),
            )

    def _toggle_fullscreen(self, _event=None) -> None:
        self.root.attributes("-fullscreen", not self.root.attributes("-fullscreen"))

    def _draw_grid(self) -> None:
        self._canvas.delete("grid")

        WAVE_X, WAVE_Y, WAVE_W, WAVE_H = self._g   # shadow constants with live geometry
        dw = WAVE_W / DIVS_X
        dh = WAVE_H / DIVS_Y
        cx = WAVE_X + WAVE_W / 2
        cy = WAVE_Y + WAVE_H / 2

        # Vertical grid lines
        for i in range(DIVS_X + 1):
            x = WAVE_X + i * dw
            is_center = (i == DIVS_X // 2)
            color = C_GRID_CTR if is_center else C_GRID
            dash = () if is_center else (2, 4)
            self._canvas.create_line(
                x, WAVE_Y, x, WAVE_Y + WAVE_H,
                fill=color, dash=dash, tags="grid",
            )
            # Ticks along center horizontal axis
            if 0 < i < DIVS_X:
                self._canvas.create_line(
                    x, cy - 4, x, cy + 4,
                    fill=C_GRID_TICK, tags="grid",
                )

        # Horizontal grid lines
        for j in range(DIVS_Y + 1):
            y = WAVE_Y + j * dh
            is_center = (j == DIVS_Y // 2)
            color = C_GRID_CTR if is_center else C_GRID
            dash = () if is_center else (2, 4)
            self._canvas.create_line(
                WAVE_X, y, WAVE_X + WAVE_W, y,
                fill=color, dash=dash, tags="grid",
            )
            # Ticks along center vertical axis
            if 0 < j < DIVS_Y:
                self._canvas.create_line(
                    cx - 4, y, cx + 4, y,
                    fill=C_GRID_TICK, tags="grid",
                )

        # Outer display border
        self._canvas.create_rectangle(
            WAVE_X, WAVE_Y, WAVE_X + WAVE_W, WAVE_Y + WAVE_H,
            outline=C_BORDER, width=1, tags="grid",
        )

        # Top-left Channel Badge
        self._canvas.create_rectangle(
            WAVE_X + 8, WAVE_Y + 8, WAVE_X + 50, WAVE_Y + 26,
            fill="#0f293d", outline=C_WAVE, tags="grid",
        )
        self._canvas.create_text(
            WAVE_X + 29, WAVE_Y + 17,
            text="CH1", font=F_AX, fill=C_WAVE, tags="grid",
        )

        # Center zero reference indicator on left margin
        self._canvas.create_text(
            WAVE_X - 10, cy,
            text="▶", font=("Segoe UI", 8), fill=C_WAVE, tags="grid",
        )

        # Time base hint
        self._canvas.create_text(
            WAVE_X + WAVE_W / 2, WAVE_Y + WAVE_H + 18,
            text="◄  TIME (t)  ►",
            font=F_AX, fill=C_TEXT_DIM, tags="grid",
        )

        self._redraw_ylabels()

    def _redraw_ylabels(self) -> None:
        self._canvas.delete("ylbl")
        try:
            vdiv = float(self._meta.get("vdiv", "2.0"))
        except ValueError:
            vdiv = 2.0

        WAVE_X, WAVE_Y, WAVE_W, WAVE_H = self._g
        dh = WAVE_H / DIVS_Y
        for j in range(DIVS_Y + 1):
            y = WAVE_Y + j * dh
            voltage = ((DIVS_Y / 2) - j) * vdiv
            if abs(voltage) < 0.001:
                label = " 0.0V"
            elif abs(voltage) < 10:
                label = f"{voltage:+.1f}V"
            else:
                label = f"{voltage:+.0f}V"

            self._canvas.create_text(
                WAVE_X - 6, y,
                text=label, font=F_AX, fill=C_TEXT_MUTED, anchor=tk.E,
                tags="ylbl",
            )

    # ══════════════════════════════════════════════════════════════════════════
    # WAVEFORM RENDERING (Canvas + Frame Generator for Video & Screenshot)
    # ══════════════════════════════════════════════════════════════════════════

    def _samples_to_points(self, samples: list[int], geom=None) -> list[float]:
        """Convert 8-bit raw samples to (x, y) points. geom=(x, y, w, h); default on-screen."""
        WAVE_X, WAVE_Y, WAVE_W, WAVE_H = geom or self._g
        if not samples or len(samples) < 2:
            return []
        try:
            vdiv = float(self._meta.get("vdiv", "2.0"))
        except ValueError:
            vdiv = 2.0

        n   = len(samples)
        cy  = WAVE_Y + WAVE_H / 2
        ppv = (WAVE_H / DIVS_Y) / vdiv   # pixels per volt

        pts: list[float] = []
        for i, raw8 in enumerate(samples):
            raw10 = raw8 << 2
            vin   = raw10 * ADC_TO_VIN
            x     = WAVE_X + (i / (n - 1)) * WAVE_W
            y     = cy - vin * ppv
            y     = max(WAVE_Y + 1, min(WAVE_Y + WAVE_H - 1, y))
            pts.extend([x, y])
        return pts

    def _render_wave(self, pts: list[float], wave_col: str, glow_col: str) -> None:
        """Render two-pass glow polyline on the Tkinter canvas."""
        self._canvas.delete("wave")
        if len(pts) < 4:
            return
        # Subtle glow pass
        self._canvas.create_line(
            pts, fill=glow_col, width=5,
            smooth=False, tags="wave",
        )
        # Sharp main trace
        self._canvas.create_line(
            pts, fill=wave_col, width=2,
            smooth=False, tags="wave",
        )

    def _draw_live_wave(self, samples: list[int]) -> None:
        pts = self._samples_to_points(samples)
        self._render_wave(pts, C_WAVE, C_WAVE_GLOW)
        if self._recording:
            self._capture_frame(self._samples_to_points(samples, REC_GEOM), C_WAVE, "LIVE")

    def _draw_frozen_wave(self, samples: list[int]) -> None:
        pts = self._samples_to_points(samples)
        self._render_wave(pts, C_WAVE_FREEZE, C_WAVE_FRZ_GL)
        if self._recording:
            self._capture_frame(self._samples_to_points(samples, REC_GEOM), C_WAVE_FREEZE, "FROZEN")

    def _demo_points(self, geom) -> list[float]:
        """Placeholder sine points for geometry (x, y, w, h)."""
        x0, y0, w, h = geom
        pts: list[float] = []
        for i in range(256):
            t   = i / 255
            val = (0.50 * math.sin(2 * math.pi * 3.0 * t + self._demo_phase)
                 + 0.12 * math.sin(2 * math.pi * 6.0 * t + self._demo_phase * 1.5))
            y = max(y0 + 1, min(y0 + h - 1, y0 + h / 2 - val * h * 0.40))
            pts.extend([x0 + t * w, y])
        return pts

    def _draw_demo_wave(self) -> None:
        """Animate clean placeholder sine wave while disconnected."""
        self._canvas.delete("wave")
        self._canvas.delete("demo_lbl")

        wx, wy, ww, wh = self._g
        pts = self._demo_points(self._g)

        self._canvas.create_line(
            pts, fill=C_WAVE_DEM_GL, width=5,
            smooth=True, tags="wave",
        )
        self._canvas.create_line(
            pts, fill=C_WAVE_DEMO, width=2,
            smooth=True, tags="wave",
        )

        self._canvas.create_text(
            wx + ww / 2,
            wy + wh / 2 + 60,
            text="DEMO MODE · Connect Arduino UNO R4 to view live signal",
            font=("Segoe UI", 9), fill="#475569",
            tags="demo_lbl",
        )

        if self._recording:
            self._capture_frame(self._demo_points(REC_GEOM), C_WAVE_DEMO, "DEMO")

        self._demo_phase -= 0.08

    # ══════════════════════════════════════════════════════════════════════════
    # DEMO & QUEUE POLLING LOOPS
    # ══════════════════════════════════════════════════════════════════════════

    def _start_demo(self) -> None:
        self._draw_demo_wave()
        if not self._connected:
            self._poll_id = self.root.after(POLL_MS, self._demo_tick)

    def _demo_tick(self) -> None:
        if not self._connected:
            self._draw_demo_wave()
            self._update_rec_badge()
            self._poll_id = self.root.after(POLL_MS, self._demo_tick)

    def _poll(self) -> None:
        try:
            while True:
                item = self._queue.get_nowait()
                kind = item["type"]

                if kind == "wave":
                    samples = item["data"]
                    if not self._frozen:
                        self._wave_data = samples
                        self._draw_live_wave(samples)

                elif kind == "meta":
                    self._meta = item["data"]
                    self._update_metrics(self._meta)
                    self._redraw_ylabels()

                elif kind == "status":
                    self._apply_conn_status(item["connected"], item["message"])

        except queue.Empty:
            pass

        self._update_rec_badge()
        self._poll_id = self.root.after(POLL_MS, self._poll)

    def _cancel_poll(self) -> None:
        if self._poll_id:
            self.root.after_cancel(self._poll_id)
            self._poll_id = None

    # ══════════════════════════════════════════════════════════════════════════
    # METRICS UPDATE
    # ══════════════════════════════════════════════════════════════════════════

    def _update_metrics(self, meta: dict) -> None:
        # Frequency
        try:
            f = float(meta.get("freq", "0"))
            fs = f"{f/1000:.3f} kHz" if f >= 1000 else f"{f:.1f} Hz"
        except ValueError:
            fs = "---"

        # Vpp
        try:
            vs = f"{float(meta.get('vpp', '0')):.3f} V"
        except ValueError:
            vs = "---"

        # Vrms
        try:
            rs = f"{float(meta.get('vrms', '0')):.3f} V"
        except ValueError:
            rs = "---"

        # V/Div
        try:
            vd = float(meta.get("vdiv", "0"))
            vds = f"{vd:.1f} V"
        except ValueError:
            vds = "---"

        # T/Div
        try:
            t = int(meta.get("tdiv", "0"))
            tds = f"{t//1000} ms" if t >= 1000 else f"{t} µs"
        except ValueError:
            tds = "---"

        state = meta.get("state", "LIVE")
        state_col = C_WAVE_FREEZE if state == "FROZEN" else C_CONN

        self._mvals["freq"].config(text=fs)
        self._mvals["vpp"].config(text=vs)
        self._mvals["vrms"].config(text=rs)
        self._mvals["vdiv"].config(text=vds)
        self._mvals["tdiv"].config(text=tds)
        self._mvals["state"].config(text=state, fg=state_col)

        # Sync adjustment labels
        try:
            self._vdiv_lbl.config(text=f"{float(meta.get('vdiv', '2.0')):.1f} V")
        except ValueError:
            pass
        try:
            t = int(meta.get("tdiv", "2000"))
            self._tdiv_lbl.config(text=f"{t//1000} ms" if t >= 1000 else f"{t} µs")
        except ValueError:
            pass

    # ══════════════════════════════════════════════════════════════════════════
    # CONNECTION MANAGEMENT
    # ══════════════════════════════════════════════════════════════════════════

    def _refresh_ports(self) -> None:
        ports = list_serial_ports()
        self._port_cb["values"] = ports
        if ports:
            if not self._port_var.get():
                self._port_var.set(ports[0])
        else:
            self._port_var.set("")

    def _toggle_connection(self) -> None:
        if self._reader and self._reader.is_alive():
            self._disconnect()
        else:
            self._connect()

    def _connect(self) -> None:
        port = self._port_var.get()
        if not port:
            self._set_status("Please select a COM port first.", error=True)
            return

        baud = int(self._baud_var.get())
        self._cancel_poll()
        self._reader = SerialReader(port, baud, self._queue)
        self._reader.start()
        self._connected = True

        self._conn_btn.config(
            text="✕ DISCONNECT", bg=C_BTN_DISC,
            activebackground="#b91c1c",
        )
        self._freeze_btn.config(state=tk.NORMAL, bg=C_BTN_FREEZE)
        self._poll()

    def _disconnect(self) -> None:
        self._cancel_poll()
        if self._reader:
            self._reader.stop()
            self._reader = None
        self._connected = False
        self._frozen    = False

        self._conn_btn.config(
            text="⚡ CONNECT", bg=C_BTN_CONN,
            activebackground="#1d4ed8",
        )
        self._freeze_btn.config(
            state=tk.DISABLED, bg="#475569", text="❄  FREEZE",
        )

        self._apply_conn_status(False, "Disconnected")
        self._start_demo()

    def _apply_conn_status(self, connected: bool, message: str) -> None:
        self._connected = connected
        if connected:
            self._conn_dot.config(text="● CONNECTED", fg=C_CONN)
            self._conn_msg.config(text=message, fg=C_TEXT_MAIN)
        else:
            self._conn_dot.config(text="● DISCONNECTED", fg=C_DISCONN)
            self._conn_msg.config(text=message, fg=C_TEXT_MUTED)
        self._set_status(message, error=not connected)

    # ══════════════════════════════════════════════════════════════════════════
    # FREEZE
    # ══════════════════════════════════════════════════════════════════════════

    def _toggle_freeze(self) -> None:
        self._frozen = not self._frozen
        if self._frozen:
            self._freeze_btn.config(
                text="▶  RESUME", bg=C_BTN_RESUME,
                activebackground="#4338ca",
            )
            if self._wave_data:
                self._draw_frozen_wave(self._wave_data)
        else:
            self._freeze_btn.config(
                text="❄  FREEZE", bg=C_BTN_FREEZE,
                activebackground="#b45309",
            )
            if self._wave_data:
                self._draw_live_wave(self._wave_data)

    # ══════════════════════════════════════════════════════════════════════════
    # V/DIV & T/DIV CONTROLS
    # ══════════════════════════════════════════════════════════════════════════

    def _send(self, cmd: str) -> None:
        if self._reader:
            self._reader.send_command(cmd)

    def _vdiv_up(self) -> None: self._send("v+")
    def _vdiv_dn(self) -> None: self._send("v-")
    def _tdiv_up(self) -> None: self._send("t+")
    def _tdiv_dn(self) -> None: self._send("t-")

    # ══════════════════════════════════════════════════════════════════════════
    # FRAME GENERATOR FOR VIDEO & SCREENSHOTS (Pixel-perfect & reliable)
    # ══════════════════════════════════════════════════════════════════════════

    def _generate_frame_image(self, pts: list[float], wave_col: str, state_text: str) -> Image.Image:
        """Render complete, pristine oscilloscope display frame to PIL Image."""
        def hex2rgb(h: str) -> tuple[int, int, int]:
            h = h.lstrip("#")
            return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))

        img = Image.new("RGB", (CANVAS_W, CANVAS_H), hex2rgb(C_CANVAS_BG))
        draw = ImageDraw.Draw(img)

        dw = WAVE_W / DIVS_X
        dh = WAVE_H / DIVS_Y
        cx = WAVE_X + WAVE_W / 2
        cy = WAVE_Y + WAVE_H / 2

        grid_rgb     = hex2rgb(C_GRID)
        grid_ctr_rgb = hex2rgb(C_GRID_CTR)
        border_rgb   = hex2rgb(C_BORDER)
        text_dim_rgb = hex2rgb(C_TEXT_DIM)
        text_mut_rgb = hex2rgb(C_TEXT_MUTED)
        wave_rgb     = hex2rgb(wave_col)

        # Vertical grid
        for i in range(DIVS_X + 1):
            x = WAVE_X + i * dw
            col = grid_ctr_rgb if (i == DIVS_X // 2) else grid_rgb
            draw.line([(x, WAVE_Y), (x, WAVE_Y + WAVE_H)], fill=col, width=1)
            if 0 < i < DIVS_X:
                draw.line([(x, cy - 4), (x, cy + 4)], fill=hex2rgb(C_GRID_TICK), width=1)

        # Horizontal grid
        for j in range(DIVS_Y + 1):
            y = WAVE_Y + j * dh
            col = grid_ctr_rgb if (j == DIVS_Y // 2) else grid_rgb
            draw.line([(WAVE_X, y), (WAVE_X + WAVE_W, y)], fill=col, width=1)
            if 0 < j < DIVS_Y:
                draw.line([(cx - 4, y), (cx + 4, y)], fill=hex2rgb(C_GRID_TICK), width=1)

        # Border
        draw.rectangle(
            [(WAVE_X, WAVE_Y), (WAVE_X + WAVE_W, WAVE_Y + WAVE_H)],
            outline=border_rgb, width=1,
        )

        # Y-axis Voltage labels
        try:
            vdiv = float(self._meta.get("vdiv", "2.0"))
        except ValueError:
            vdiv = 2.0

        for j in range(DIVS_Y + 1):
            y = WAVE_Y + j * dh
            voltage = ((DIVS_Y / 2) - j) * vdiv
            if abs(voltage) < 0.001:
                label = " 0.0V"
            elif abs(voltage) < 10:
                label = f"{voltage:+.1f}V"
            else:
                label = f"{voltage:+.0f}V"
            draw.text((WAVE_X - 44, y - 6), label, fill=text_mut_rgb, font=self._pil_font_small)

        # CH1 Badge
        draw.rectangle(
            [(WAVE_X + 8, WAVE_Y + 8), (WAVE_X + 50, WAVE_Y + 26)],
            fill=hex2rgb("#0f293d"), outline=wave_rgb, width=1,
        )
        draw.text((WAVE_X + 16, WAVE_Y + 11), "CH1", fill=wave_rgb, font=self._pil_font_small)

        # Info overlay on top right of video frame
        vdiv_str = f"{vdiv:.1f} V/div"
        try:
            tdiv_val = int(self._meta.get("tdiv", "2000"))
            tdiv_str = f"{tdiv_val//1000} ms/div" if tdiv_val >= 1000 else f"{tdiv_val} µs/div"
        except ValueError:
            tdiv_str = "2 ms/div"

        info_text = f"{vdiv_str}  ·  {tdiv_str}  ·  [{state_text}]"
        draw.text((WAVE_X + WAVE_W - 220, WAVE_Y + 11), info_text, fill=text_mut_rgb, font=self._pil_font_small)

        # Waveform polyline
        if pts and len(pts) >= 4:
            pts_tuples = [(pts[k], pts[k + 1]) for k in range(0, len(pts), 2)]
            draw.line(pts_tuples, fill=wave_rgb, width=2)

        return img

    def _capture_frame(self, pts: list[float], wave_col: str, state_text: str) -> None:
        """Capture current frame into active cv2.VideoWriter."""
        if not self._recording or not self._video_writer:
            return

        pil_img = self._generate_frame_image(pts, wave_col, state_text)
        frame_bgr = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
        self._last_frame_bgr = frame_bgr
        self._video_writer.write(frame_bgr)
        self._record_frames += 1

    # ══════════════════════════════════════════════════════════════════════════
    # SCREENSHOT CAPTURE (PNG)
    # ══════════════════════════════════════════════════════════════════════════

    def _take_screenshot(self) -> None:
        try:
            out_dir = os.path.join(os.path.dirname(__file__), "screenshots")
            os.makedirs(out_dir, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = os.path.join(out_dir, f"scope_{ts}.png")

            # Obtain current waveform points (fixed screenshot geometry)
            if self._connected and self._wave_data:
                pts = self._samples_to_points(self._wave_data, REC_GEOM)
                col = C_WAVE_FREEZE if self._frozen else C_WAVE
                st  = "FROZEN" if self._frozen else "LIVE"
            else:
                pts = self._demo_points(REC_GEOM)
                col = C_WAVE_DEMO
                st  = "DEMO"

            img = self._generate_frame_image(pts, col, st)
            img.save(path)
            self._set_status(f"📷 Screenshot saved → screenshots/scope_{ts}.png")
        except Exception as exc:
            self._set_status(f"Screenshot failed: {exc}", error=True)

    # ══════════════════════════════════════════════════════════════════════════
    # MP4 VIDEO RECORDING
    # ══════════════════════════════════════════════════════════════════════════

    def _toggle_record(self) -> None:
        if self._recording:
            self._stop_recording()
        else:
            self._start_recording()

    def _start_recording(self) -> None:
        try:
            out_dir = os.path.join(os.path.dirname(__file__), "recordings")
            os.makedirs(out_dir, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            self._record_path = os.path.join(out_dir, f"scope_recording_{ts}.mp4")

            # Initialize OpenCV VideoWriter with MP4V codec at 20 FPS
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            self._video_writer = cv2.VideoWriter(
                self._record_path, fourcc, 20.0, (CANVAS_W, CANVAS_H),
            )

            if not self._video_writer.isOpened():
                raise RuntimeError("Failed to open OpenCV VideoWriter with mp4v codec.")

            self._recording         = True
            self._record_start_time = time.time()
            self._record_frames     = 0

            self._rec_btn.config(
                text="⏹  STOP REC", bg=C_BTN_STOP,
                activebackground="#5c0d25",
            )
            self._set_status(f"⏺ Recording MP4 video → recordings/scope_recording_{ts}.mp4")
        except Exception as exc:
            self._recording = False
            self._set_status(f"Recording start failed: {exc}", error=True)

    def _stop_recording(self) -> None:
        if not self._recording:
            return
        self._recording = False
        duration = max(0.1, time.time() - self._record_start_time)
        frames   = self._record_frames

        if self._video_writer:
            self._video_writer.release()
            self._video_writer = None

        self._rec_badge.config(text="")
        self._rec_btn.config(
            text="⏺  RECORD MP4", bg=C_BTN_REC,
            activebackground="#9f1239",
        )

        name = os.path.basename(self._record_path)
        self._set_status(f"✔ Saved MP4 Video ({duration:.1f}s, {frames} frames) → recordings/{name}")

    def _update_rec_badge(self) -> None:
        if not self._recording:
            return
        elapsed = int(time.time() - self._record_start_time)
        m, s    = divmod(elapsed, 60)
        self._blink_on = not self._blink_on
        dot = "⏺" if self._blink_on else " "
        self._rec_badge.config(text=f"{dot} REC {m:02d}:{s:02d} ({self._record_frames} f)")

    # ══════════════════════════════════════════════════════════════════════════
    # STATUS BAR & RUN LIFECYCLE
    # ══════════════════════════════════════════════════════════════════════════

    def _set_status(self, msg: str, error: bool = False) -> None:
        self._status_lbl.config(
            text=msg,
            fg=C_DISCONN if error else C_TEXT_MUTED,
        )

    def run(self) -> None:
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.mainloop()

    def _on_close(self) -> None:
        self._cancel_poll()
        if self._recording:
            self._stop_recording()
        if self._reader:
            self._reader.stop()
        self.root.destroy()
