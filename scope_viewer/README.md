# scope_viewer

Optional add-on for the [Arduino oscilloscope](../README.md).

Optional PC viewer for the Arduino UNO R4 oscilloscope. Streams the ADC waveform over serial into a Tkinter window (live trace, freeze, V/div and T/div control, PNG screenshot, MP4 recording). The Arduino project is the main thing; this is an add-on.

## Use

1. Flash `Oscilloscope/Oscilloscope.ino` (the serial-streaming version of the main sketch, no TFT output needed) to the UNO R4 (same wiring as `oscilloscope_code`, signal on `A0`). To return to TFT-only mode, flash `../oscilloscope_code/oscilloscope_code.ino`.
2. `pip install -r viewer/requirements.txt`
3. `python viewer/viewer.py`

The window starts maximized. `F11` toggles full screen, `Esc` leaves it. With no board connected it shows an animated demo wave.

## Serial protocol (115200 baud)

| Direction | Line | Example |
|---|---|---|
| Arduino to PC | `WAVE:<v0>,...,<v127>` (raw 8-bit samples) | `WAVE:128,130,145,...` |
| Arduino to PC | `META:vdiv=,tdiv=,freq=,vpp=,vrms=,state=` | `META:vdiv=2.0,tdiv=2000,...` |
| PC to Arduino | `v+` `v-` `t+` `t-` | |

Voltage: `(raw8 << 2) * ADC_VREF / 1023 / DIVIDER_RATIO`.

## Calibration

If your divider differs, change `ADC_VREF` and `DIVIDER_RATIO` in both `Oscilloscope/Oscilloscope.ino` and `viewer/oscilloscope_ui.py` (defaults 5.0 V and 0.4, range 0-12.5 V).

Screenshots and recordings are saved under `viewer/screenshots/` and `viewer/recordings/` (git-ignored) at a fixed 920x460 size regardless of window size.
