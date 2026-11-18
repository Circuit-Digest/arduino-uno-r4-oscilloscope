"""
serial_reader.py — scope_viewer
────────────────────────────────
Background thread that reads WAVE: and META: packets from the
Arduino Oscilloscope.ino sketch and pushes parsed data into a
thread-safe queue for consumption by the Tkinter UI thread.
"""

import threading
import queue
import time
from typing import Optional

import serial
import serial.tools.list_ports


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def list_serial_ports() -> list[str]:
    """Return a sorted list of available serial port device names."""
    ports = serial.tools.list_ports.comports()
    return sorted([p.device for p in ports])


# ──────────────────────────────────────────────────────────────────────────────
# SerialReader
# ──────────────────────────────────────────────────────────────────────────────

class SerialReader(threading.Thread):
    """
    Daemon thread that connects to a serial port and continuously reads
    WAVE: and META: lines, placing parsed dicts onto *data_queue*.

    Queue item schema
    -----------------
    Wave packet:
        {"type": "wave", "data": list[int]}   # 128 values, 0-255

    Meta packet:
        {"type": "meta", "data": dict[str, str]}
        Keys: vdiv, tdiv, freq, vpp, vrms, state

    Status packet (connection events):
        {"type": "status", "connected": bool, "message": str}
    """

    RECONNECT_DELAY_S = 2.0   # seconds between reconnect attempts

    def __init__(self, port: str, baud: int, data_queue: queue.Queue) -> None:
        super().__init__(daemon=True, name="SerialReader")
        self.port       = port
        self.baud       = baud
        self.data_queue = data_queue

        self._stop_event = threading.Event()
        self._ser: Optional[serial.Serial] = None

        # Public state (safe to read from main thread — primitive assignment is atomic in CPython)
        self.connected     = False
        self.error_message = ""

    # ── Public API ────────────────────────────────────────────────────────────

    def stop(self) -> None:
        """Signal the thread to stop and close the port."""
        self._stop_event.set()
        if self._ser and self._ser.is_open:
            try:
                self._ser.close()
            except Exception:
                pass

    def send_command(self, cmd: str) -> None:
        """
        Send a command string to the Arduino (non-blocking).
        Commands: 'v+', 'v-', 't+', 't-', 'f'
        """
        if self._ser and self._ser.is_open:
            try:
                self._ser.write((cmd.strip() + "\n").encode("ascii"))
            except serial.SerialException:
                pass

    # ── Thread body ───────────────────────────────────────────────────────────

    def run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._connect_and_read()
            except Exception as exc:
                self._set_disconnected(str(exc))
                self._stop_event.wait(self.RECONNECT_DELAY_S)

    def _connect_and_read(self) -> None:
        with serial.Serial(self.port, self.baud, timeout=1) as ser:
            self._ser = ser
            self._set_connected()

            while not self._stop_event.is_set():
                try:
                    raw = ser.readline()
                    if not raw:
                        continue
                    line = raw.decode("ascii", errors="ignore").strip()
                    self._dispatch(line)
                except serial.SerialException as exc:
                    raise exc  # bubble up to trigger reconnect

    def _dispatch(self, line: str) -> None:
        if line.startswith("WAVE:"):
            self._parse_wave(line)
        elif line.startswith("META:"):
            self._parse_meta(line)

    def _parse_wave(self, line: str) -> None:
        """Parse WAVE:<v0>,<v1>,...,<v127> → push {"type":"wave", "data":[...]}"""
        try:
            values = [int(v) for v in line[5:].split(",")]
            if len(values) == 128:
                self.data_queue.put_nowait({"type": "wave", "data": values})
        except (ValueError, queue.Full):
            pass

    def _parse_meta(self, line: str) -> None:
        """Parse META:k=v,k=v,... → push {"type":"meta", "data":{...}}"""
        try:
            meta: dict[str, str] = {}
            for pair in line[5:].split(","):
                if "=" in pair:
                    k, v = pair.split("=", 1)
                    meta[k.strip()] = v.strip()
            if meta:
                self.data_queue.put_nowait({"type": "meta", "data": meta})
        except (ValueError, queue.Full):
            pass

    # ── Internal state helpers ─────────────────────────────────────────────────

    def _set_connected(self) -> None:
        self.connected     = True
        self.error_message = ""
        self.data_queue.put_nowait({
            "type":      "status",
            "connected": True,
            "message":   f"Connected to {self.port} @ {self.baud} baud",
        })

    def _set_disconnected(self, reason: str) -> None:
        self.connected     = False
        self.error_message = reason
        self.data_queue.put_nowait({
            "type":      "status",
            "connected": False,
            "message":   reason,
        })
