# 🔬 Arduino Mini Oscilloscope

> A compact, real-time digital oscilloscope built with the **Arduino Uno R4 Minima** and a **2.0" ILI9225 SPI TFT display** — featuring flicker-free waveform rendering, live signal measurements, and an intuitive rotary encoder interface.

---

## 📸 Preview

> *(Add a photo of your oscilloscope here)*

---

## ✨ Features

- 📈 **Real-time waveform rendering** — smooth, flicker-free display using an off-screen 2-bit canvas buffer
- ⚡ **Signal measurements** — live Vpp, Vrms, and frequency detection displayed in the header
- 🎛️ **Rotary encoder navigation** — cycle through all settings with a single knob
- 🔒 **Freeze / Hold mode** — selectable via encoder or dedicated button
- 📐 **Adjustable Volts/Div** — 0.1V, 0.2V, 0.5V, 1V, 2V, 3V, 5V, 10V
- ⏱️ **Adjustable Time/Div** — 200µs, 500µs, 1ms, 2ms, 5ms, 10ms
- 🕹️ **X / Y offset control** — pan the waveform horizontally and vertically
- 🔄 **Display rotation** — flip orientation on-the-fly from the Settings menu
- 📟 **Serial telemetry** — live debug output over UART at 9600 baud

---

## 🛒 Hardware Requirements

| Component | Details |
|---|---|
| **Microcontroller** | Arduino Uno R4 Minima |
| **Display** | 2.0" ILI9225 SPI TFT (176×220 px) |
| **Input control** | Rotary encoder with push button |
| **Freeze button** | Momentary push button (dedicated) |
| **Signal input** | Analog voltage via voltage divider on A0 |

---

## 📌 Wiring / Pin Map

### 🖥️ Display (ILI9225 SPI TFT)
| TFT Pin | Arduino Pin |
|---|---|
| RS / DC | D6 |
| RST | D7 |
| CS | D8 |
| SDA / MOSI | D11 |
| CLK / SCK | D13 |

### 🎛️ Rotary Encoder
| Encoder Pin | Arduino Pin |
|---|---|
| CLK | D2 |
| DT | D3 |
| Switch | D4 |

### 🔘 Dedicated Freeze Button
| Button | Arduino Pin |
|---|---|
| Freeze / Pause | D5 |

### 🔌 Signal Input
| Signal | Arduino Pin |
|---|---|
| Oscilloscope Input | A0 |

> ⚠️ **Important:** A0 requires a **voltage divider** circuit to protect the Arduino ADC from over-voltage. See calibration section below.

---

## 🎮 Controls

| Action | Result |
|---|---|
| **Rotate encoder** | Adjust the currently selected parameter |
| **Short press encoder** | Cycle to next mode: `V/Div → T/Div → X → Y → FREEZE → SETTINGS` |
| **Select FREEZE + rotate** | Toggle waveform freeze on/off |
| **Press D5 button** | Instant freeze / unfreeze from any mode |
| **Select SETTINGS + rotate** | Flip display orientation (fix upside-down screens) |

---

## 📐 Calibration

### Voltage Divider
The signal input on **A0** uses a resistor voltage divider to scale the input voltage down to 0–5V (Arduino ADC range). You **must** configure the divider ratio to match your circuit:

```cpp
// In oscilloscope_code.ino — adjust to match your resistor values
const float ADC_VREF      = 5.0;
const float DIVIDER_RATIO = 0.4;  // <- Change this for your circuit
```

**How to calculate `DIVIDER_RATIO`:**
```
DIVIDER_RATIO = R2 / (R1 + R2)
```
For example, with R1 = 15kΩ and R2 = 10kΩ:
```
DIVIDER_RATIO = 10000 / (15000 + 10000) = 0.4
```

---

## 🗂️ Project Structure

```
oscilloscope_code/
│
├── oscilloscope_code.ino          <- Main sketch
│
└── src/
    └── src/
        ├── TFT_22_ILI9225_Local.h      <- Patched library header
        ├── TFT_22_ILI9225_Local.cpp    <- Patched library implementation
        ├── DefaultFonts.c              <- Display font data
        └── gfxfont.h                   <- Font struct definitions
```

---

## 📦 Library — Why a Local Copy?

This project uses a **locally patched fork** of the [`TFT_22_ILI9225` library (v1.4.5)](https://github.com/Nkawu/TFT_22_ILI9225) by Nkawu, stored inside `src/src/`. The original library was **not compatible** with the Arduino Uno R4 Minima (Renesas RA4M1 architecture) and required the following fixes:

### Patches Applied

| File | Change | Reason |
|---|---|---|
| `TFT_22_ILI9225_Local.cpp` | Wrapped `#include "wiring_private.h"` with `__has_include` guard | `wiring_private.h` does not exist on the Renesas platform — causes compile error |
| `TFT_22_ILI9225_Local.h` | Added `ARDUINO_ARCH_RENESAS` to `#undef USE_FAST_PINIO` | `USE_FAST_PINIO` depends on SAMD-specific `RwReg` type, unavailable on Renesas |
| `DefaultFonts.c` | Added `#include <Arduino.h>` and `#ifndef PROGMEM` fallback | Font file is plain C; Renesas C compiler does not natively know Arduino types |
| `TFT_22_ILI9225_Local.h/.cpp` | **Added new `draw2BitBitmap()` method** | Custom high-speed method that streams the 2-bit canvas to the display in one SPI transaction (~13ms per frame), enabling flicker-free rendering |

> ⚠️ **Do NOT install the global `TFT_22_ILI9225` library** from the Arduino Library Manager. It will conflict with the local patched version. The correct library is already bundled in this repository inside `src/src/`.

---

## ⚙️ How It Works

### Flicker-Free Rendering (Canvas Buffer)
Instead of drawing directly to the screen (which causes flickering), the sketch:
1. Clears a **5,200-byte RAM canvas** (2 bits per pixel — 4 colors, 4 pixels per byte)
2. Draws the grid, divisions, and waveform **into the canvas in RAM**
3. Pushes the entire canvas to the display in **one fast SPI transaction** via `draw2BitBitmap()`

This results in smooth ~13ms frame updates with zero visible flicker.

### Frequency Detection
Zero-crossing detection is used on the captured waveform buffer to estimate signal frequency:
- Finds all rising-edge zero crossings using linear interpolation
- Averages the period across all detected cycles
- Converts to Hz using the actual measured sample rate

### Encoder State Machine
Both CLK and DT pins trigger interrupts on `CHANGE`. A **Gray code state machine** decodes the quadrature signal and only registers one step per physical detent click — completely filtering out contact bounce without additional hardware debounce capacitors.

---

## 🚀 Getting Started

### 1. Clone the Repository
```bash
git clone https://github.com/YOUR_USERNAME/arduino-mini-oscilloscope.git
```

### 2. Open in Arduino IDE
Open `oscilloscope_code/oscilloscope_code.ino` in **Arduino IDE 2.x**.

### 3. Select the Board
- Go to **Tools → Board → Arduino Uno R4 Minima**
- Select your correct **COM port**

### 4. Do NOT install the TFT library separately
The patched library is already included locally in `src/src/`. Installing the global version will cause a conflict.

### 5. Upload
Click **Upload** and open Serial Monitor at **9600 baud** for live telemetry.

---

## 📺 Display Layout

```
+------------------------------------------+
|  MINI OSCILLOSCOPE                        |  <- Title (yellow)
|  VPP:3.27  VRMS:2.05  V  1000Hz          |  <- Live measurements (white)
+------------------------------------------+
|                                          |
|    ~  Real-time waveform (green)  ~      |  <- Graph area
|                                          |
+------------------------------------------+
|  [2.0V]  [200us]  [X:0]  [Y:0]          |  <- Mode boxes row 1
|  [ ⚙ ]  [ RUNNING / FROZEN ]            |  <- Settings + Freeze row 2
+------------------------------------------+
```

The **currently active mode box** is highlighted with a **yellow border** and **blue fill**. All other boxes show a white border with cyan text.

---

## 📊 Specifications

| Parameter | Value |
|---|---|
| ADC Resolution | 10-bit (0–1023) |
| Sample Buffer | 128 samples per frame |
| Min Time/Div | 200 µs |
| Max Time/Div | 10 ms |
| Min Volts/Div | 0.1 V |
| Max Volts/Div | 10 V |
| Frame Update Speed | ~13 ms (canvas push) |
| Text / Status Update Rate | Every 300 ms |
| Serial Baud Rate | 9600 |

---

## 📝 License

This project is open source. The bundled `TFT_22_ILI9225` library is originally licensed under the **LGPL-2.1 License** by [Nkawu](https://github.com/Nkawu/TFT_22_ILI9225).

---

## 🙌 Acknowledgements

- [`TFT_22_ILI9225`](https://github.com/Nkawu/TFT_22_ILI9225) by Nkawu — base TFT display library (locally patched for Renesas compatibility + custom `draw2BitBitmap()`)
- Arduino community for Uno R4 Minima board support

---

*Built with ❤️ for makers and electronics enthusiasts.*
