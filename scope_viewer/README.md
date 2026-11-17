# scope_viewer

A modern Python + Tkinter PC oscilloscope viewer for the **Arduino UNO R4 Mini Oscilloscope** project.  
Streams live waveform data from the Arduino over serial and displays it in a clean, professional dark digital oscilloscope interface.

> **The original `oscilloscope_code.ino` is never modified.**  
> This is a standalone companion project with its own Arduino sketch.

---

## Features

- **Clean & Modern Digital Theme**: Slate/Navy aesthetic with high-contrast electric cyan live trace and warm amber frozen hold (no green CRT clutter).
- **MP4 Video Recording**: Record high-fps oscilloscope screen captures directly to `.mp4` format using OpenCV and PIL.
- **Crystal-Clear Screenshots**: Save pixel-perfect PNG captures of the oscilloscope grid, voltage labels, and waveforms anytime.
- **Hardware Sync**: Real-time V/Div and T/Div adjustment buttons that send commands back to the Arduino.
- **Live Measurements**: 6-metric status strip showing Frequency, Vpp, Vrms, V/Div, T/Div, and Acquisition state.
- **Demo Mode**: Smooth animated sine wave when disconnected so you can explore the interface and test recording anytime.

---

## Project Structure

```
scope_viewer/
├── pc_stream/
│   └── pc_stream.ino       ← Companion Arduino sketch (flash this for PC mode)
└── viewer/
    ├── viewer.py            ← Entry point  →  python viewer.py
    ├── serial_reader.py     ← Background serial thread
    ├── oscilloscope_ui.py   ← Tkinter UI, canvas & MP4 video generator
    ├── requirements.txt     ← Python dependencies
    ├── recordings/          ← Saved MP4 video recordings
    └── screenshots/         ← Saved PNG screenshots
```

---

## How to Use

### Step 1 — Flash the Companion Sketch

Open `pc_stream/pc_stream.ino` in the Arduino IDE and flash it to your **Arduino UNO R4**.

> **Same wiring as the original sketch** — signal input on `A0`, no display needed.

To go back to the TFT display, simply re-flash `oscilloscope_code/oscilloscope_code.ino`.

### Step 2 — Install Python Dependencies

```bash
cd scope_viewer/viewer
pip install -r requirements.txt
```

Dependencies include:
- `pyserial >= 3.5`
- `Pillow >= 9.0`
- `opencv-python >= 4.8`
- `numpy >= 1.20`

### Step 3 — Run the Viewer

```bash
python viewer.py
```

---

## Interface Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  SCOPE VIEWER                 Arduino UNO R4 · Digital Oscilloscope         │
├─────────────────────────────────────────────────────────────────────────────┤
│  PORT: [COM3 ▼] [⟳]   BAUD: [115200 ▼]   [⚡ CONNECT]                       │
├─────────────────────────────────────────────────────────────────────────────┤
│  [❄ FREEZE]   │   [📷 SCREENSHOT]   [⏺ RECORD MP4]   ⏺ REC 00:04 (80 f)     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   +8.0V ┤  [CH1]                           2.0 V/div · 2 ms/div · [LIVE]    │
│   +4.0V ┤  ·  ·  ·  ·  ·  ·  ·  ·  ·  ·                                     │
│   +2.0V ┤       ╭───╮         ╭───╮         ╭──                             │
│    0.0V ┼───────╯───╰─────────╯───╰─────────╯─── ◄ TIME (t) ►               │
│   -2.0V ┤                                                                   │
│   -4.0V ┤  ·  ·  ·  ·  ·  ·  ·  ·  ·  ·                                     │
│   -8.0V ┤                                                                   │
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│  VOLTS/DIV: [▼] 2.0 V [▲]   TIME/DIV: [▼] 2 ms [▲]   [CH1 · Analog In (A0)] │
├─────────────────────────────────────────────────────────────────────────────┤
│  FREQUENCY   PEAK-TO-PEAK   RMS VOLTAGE   V / DIV   T / DIV   ACQUISITION   │
│  1.000 kHz   5.000 V        1.768 V       2.0 V     2 ms      LIVE          │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Serial Protocol

The companion sketch streams two types of lines at **115200 baud**:

| Line | Format | Example |
|------|--------|---------|
| Waveform | `WAVE:<v0>,<v1>,...,<v127>` | `WAVE:128,130,145,...` |
| Metadata | `META:vdiv=X,tdiv=X,freq=X,vpp=X,vrms=X,state=X` | `META:vdiv=2.0,tdiv=2000,...` |

Values in `WAVE:` are raw 8-bit ADC samples (0–255).  
The Python viewer reconstructs voltage using: `voltage = (raw8 << 2) * (5.0 / 1023.0 / 0.4)`

---

## Interactive Controls

| Control | Action | Details |
|---------|--------|---------|
| `⚡ CONNECT` / `✕ DISCONNECT` | Toggle serial connection | Auto-enumerates ports with refresh button |
| `❄ FREEZE` / `▶ RESUME` | Toggle waveform hold | Shows frozen waveform in high-visibility warm amber |
| `📷 SCREENSHOT` | Save PNG image | Stored in `viewer/screenshots/scope_TIMESTAMP.png` |
| `⏺ RECORD MP4` | Capture live video | Recorded at 20 FPS into `viewer/recordings/scope_recording_TIMESTAMP.mp4` |
| `VOLTS / DIV [▲][▼]` | Adjust amplitude scale | Sends `v+` / `v-` to Arduino |
| `TIME / DIV [▲][▼]` | Adjust horizontal timebase | Sends `t+` / `t-` to Arduino |

---

## ADC Calibration

If your voltage divider differs from the default, edit these constants in **both** files:

| File | Constants |
|------|-----------|
| `pc_stream/pc_stream.ino` | `ADC_VREF`, `DIVIDER_RATIO` |
| `viewer/oscilloscope_ui.py` | `ADC_VREF`, `DIVIDER_RATIO` |

Default values match the original `oscilloscope_code.ino`:
- `ADC_VREF = 5.0 V`
- `DIVIDER_RATIO = 0.4`  → input range: 0 – 12.5 V
