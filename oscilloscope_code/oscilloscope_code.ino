/*
  Arduino Uno R4 Minima Mini Oscilloscope
  Display: 2.0" ILI9225 SPI TFT (176x220)

  Controls:
  D2  - Rotary Encoder CLK
  D3  - Rotary Encoder DT
  D4  - Rotary Encoder Switch
  D5  - Freeze / Pause Button (dedicated)

  Display:
  D6  - RS / DC
  D7  - RST
  D8  - CS
  D11 - SDA / MOSI
  D13 - CLK / SCK

  Input:
  A0  - Oscilloscope Input
*/

#include <Arduino.h>
#include <SPI.h>
#include "src/src/TFT_22_ILI9225_Local.h"
#include <math.h>

// =====================================================
// DISPLAY PINS
// =====================================================

#define TFT_RST  7
#define TFT_RS   6
#define TFT_CS   8
#define TFT_SDI  11
#define TFT_CLK  13

TFT_22_ILI9225 tft(
  TFT_RST,
  TFT_RS,
  TFT_CS,
  TFT_SDI,
  TFT_CLK
);

// =====================================================
// PIN DEFINITIONS
// =====================================================

const uint8_t PIN_SCOPE_INPUT = A0;

const uint8_t PIN_ENC_CLK   = 2;
const uint8_t PIN_ENC_DT    = 3;
const uint8_t PIN_ENC_SW    = 4;
const uint8_t PIN_PAUSE_BTN = 5;  // Dedicated freeze / pause button


// =====================================================
// DISPLAY ROTATION & SETTINGS
// =====================================================
// 0 = Portrait (0 degrees, default)
// 1 = Landscape (90 degrees rotated right)
// 2 = Reverse Portrait (180 degrees rotated)
// 3 = Reverse Landscape (270 degrees rotated left)
#define DISPLAY_ROTATION 1

#if (DISPLAY_ROTATION == 1) || (DISPLAY_ROTATION == 3)
  #define IS_LANDSCAPE true
  const int SCREEN_W = 220;
  const int SCREEN_H = 176;
  const int GRAPH_X = 10;
  const int GRAPH_Y = 30;
  const int GRAPH_W = 200;
  const int GRAPH_H = 100;
  const int STATUS_Y = 135;
#else
  #define IS_LANDSCAPE false
  const int SCREEN_W = 176;
  const int SCREEN_H = 220;
  const int GRAPH_X = 8;
  const int GRAPH_Y = 35;
  const int GRAPH_W = 160;
  const int GRAPH_H = 130;
  const int STATUS_Y = 175;
#endif

#if IS_LANDSCAPE
  uint8_t displayRotation = 3; // Default to 3 (Landscape reversed) since 1 was upside down
#else
  uint8_t displayRotation = 2; // Default to 2 (Portrait reversed) since 0 was upside down
#endif

// Header
const int HEADER_H = 28;


// =====================================================
// ADC CALIBRATION
// =====================================================

// Adjust these depending on your voltage divider circuit

const float ADC_VREF = 5.0;
const float DIVIDER_RATIO = 0.4;

const float ADC_TO_VIN =
  ADC_VREF / 1023.0 / DIVIDER_RATIO;


// =====================================================
// WAVEFORM BUFFER & CANVAS
// =====================================================

const uint8_t BUF_LEN = 128;

uint8_t sampleBuf[BUF_LEN];
uint8_t canvas[5200];

bool paused = false;


// =====================================================
// SIGNAL METRICS
// =====================================================

float signalFreq = 0.0;
float signalVpp  = 0.0;
float signalVrms = 0.0;


// =====================================================
// PARAMETER MODES
// =====================================================

enum Mode
{
  VOLTS_DIV = 0,
  TIME_DIV,
  X_POS,
  Y_POS,
  FREEZE,
  SETTINGS,
  MODE_COUNT
};

uint8_t currentMode = VOLTS_DIV;


// =====================================================
// VOLTS / DIV SETTINGS
// =====================================================

const float voltsDivPresets[] =
{
  0.1,
  0.2,
  0.5,
  1.0,
  2.0,
  3.0,
  5.0,
  10.0
};

const uint8_t VOLTS_DIV_COUNT = 8;

int8_t voltsDivIndex = 4;  // Default: 2.0 V/div


// =====================================================
// TIME / DIV SETTINGS
// =====================================================

const unsigned int timeDivPresetsUs[] =
{
  200,
  500,
  1000,
  2000,
  5000,
  10000
};

const uint8_t TIME_DIV_COUNT = 6;

int8_t timeDivIndex = 3;


// =====================================================
// POSITION SETTINGS
// =====================================================

int8_t xOffset = 0;
int8_t yOffset = 0;


// =====================================================
// TELEMETRY AND SCREEN TIMING
// =====================================================

unsigned long lastSerialPrintMs = 0;
unsigned long lastRedrawMs = 0;


// =====================================================
// ENCODER INTERRUPT
// =====================================================

volatile int8_t encoderDelta = 0;


void encoderISR()
{
  static uint8_t lastState = 0;
  static int8_t subSteps = 0;

  uint8_t clk = digitalRead(PIN_ENC_CLK);
  uint8_t dt  = digitalRead(PIN_ENC_DT);
  uint8_t currentState = (clk << 1) | dt;

  if (currentState != lastState)
  {
    // Clockwise transitions: 00 -> 10 -> 11 -> 01 -> 00
    // Counter-clockwise transitions: 00 -> 01 -> 11 -> 10 -> 00
    if ((lastState == 0b00 && currentState == 0b10) ||
        (lastState == 0b10 && currentState == 0b11) ||
        (lastState == 0b11 && currentState == 0b01) ||
        (lastState == 0b01 && currentState == 0b00))
    {
      subSteps++;
    }
    else if ((lastState == 0b00 && currentState == 0b01) ||
             (lastState == 0b01 && currentState == 0b11) ||
             (lastState == 0b11 && currentState == 0b10) ||
             (lastState == 0b10 && currentState == 0b00))
    {
      subSteps--;
    }

    // A standard detent (click) is 4 state changes.
    // If it accumulates to 4 or -4, we register a single step.
    if (subSteps >= 4)
    {
      encoderDelta++;
      subSteps = 0;
    }
    else if (subSteps <= -4)
    {
      encoderDelta--;
      subSteps = 0;
    }

    lastState = currentState;
  }
}


// =====================================================
// BUTTON DEBOUNCE
// =====================================================

bool lastSwState = HIGH;
unsigned long lastSwMs = 0;


// =====================================================
// SERIAL TELEMETRY
// =====================================================

void printSerialTelemetry()
{
  Serial.print(F("[MODE]: "));

  switch (currentMode)
  {
    case VOLTS_DIV:
      Serial.print(F("VOLTS/DIV"));
      break;

    case TIME_DIV:
      Serial.print(F("TIME/DIV"));
      break;

    case X_POS:
      Serial.print(F("X-POSITION"));
      break;

    case Y_POS:
      Serial.print(F("Y-POSITION"));
      break;

    case SETTINGS:
      Serial.print(F("SETTINGS"));
      break;
  }

  Serial.print(F(" | V/Div: "));
  Serial.print(voltsDivPresets[voltsDivIndex], 1);

  Serial.print(F("V | T/Div: "));
  Serial.print(timeDivPresetsUs[timeDivIndex]);
  Serial.print(F("us"));

  Serial.print(F(" | X: "));
  Serial.print(xOffset);

  Serial.print(F(" | Y: "));
  Serial.print(yOffset);

  Serial.print(F(" | Freq: "));
  Serial.print(signalFreq, 1);
  Serial.print(F("Hz"));

  Serial.print(F(" | Vpp: "));
  Serial.print(signalVpp, 2);
  Serial.print(F("V"));

  Serial.print(F(" | Vrms: "));
  Serial.print(signalVrms, 2);
  Serial.print(F("V"));

  Serial.print(F(" | State: "));

  Serial.println(
    paused ?
    F("*** FROZEN ***") :
    F("RUNNING")
  );
}


// =====================================================
// HANDLE ENCODER AND BUTTONS
// =====================================================

void handleInputs()
{
  noInterrupts();

  int8_t delta = encoderDelta;

  encoderDelta = 0;

  interrupts();


  // ----------------------------------
  // Rotary Encoder
  // ----------------------------------

  if (delta != 0)
  {
    int direction =
      (delta > 0) ? 1 : -1;

    switch (currentMode)
    {
      case VOLTS_DIV:

        voltsDivIndex =
          constrain(
            voltsDivIndex + direction,
            0,
            VOLTS_DIV_COUNT - 1
          );

        break;


      case TIME_DIV:

        timeDivIndex =
          constrain(
            timeDivIndex + direction,
            0,
            TIME_DIV_COUNT - 1
          );

        break;


      case X_POS:

        xOffset =
          constrain(
            xOffset + direction * 2,
            -60,
            60
          );

        break;


      case Y_POS:

        yOffset =
          constrain(
            yOffset + direction * 2,
            -50,
            50
          );

        break;

      case FREEZE:
        // Encoder rotation toggles freeze
        paused = !paused;
        break;

      case SETTINGS:
        #if IS_LANDSCAPE
        displayRotation = (displayRotation == 1) ? 3 : 1;
        #else
        displayRotation = (displayRotation == 0) ? 2 : 0;
        #endif
        tft.setOrientation(displayRotation);
        tft.clear();
        drawStaticUI();
        break;
    }

    printSerialTelemetry();
  }


  // ----------------------------------
  // Encoder Push Button (mode cycle — short press only)
  // ----------------------------------

  static bool swStable = HIGH;
  static bool swPressed = false;
  const unsigned long DEBOUNCE_DELAY = 40;

  bool swReading = digitalRead(PIN_ENC_SW);

  // Debounce the switch reading using global state variables
  if (swReading != lastSwState)
  {
    lastSwMs = millis();
    lastSwState = swReading;
  }

  if ((millis() - lastSwMs) > DEBOUNCE_DELAY)
  {
    // If the state has changed after the debounce period
    if (swReading != swStable)
    {
      swStable = swReading;

      if (swStable == LOW)
      {
        swPressed = true;
      }
      else
      {
        // Button released — cycle mode
        if (swPressed)
        {
          currentMode = (currentMode + 1) % MODE_COUNT;
          printSerialTelemetry();
          swPressed = false;
        }
      }
    }
  }


  // ----------------------------------
  // Dedicated Pause / Freeze Button (D5)
  // ----------------------------------

  static bool pauseBtnStable = HIGH;
  static bool lastPauseBtnState = HIGH;
  static unsigned long lastPauseBtnMs = 0;

  bool pauseReading = digitalRead(PIN_PAUSE_BTN);

  if (pauseReading != lastPauseBtnState)
  {
    lastPauseBtnMs = millis();
    lastPauseBtnState = pauseReading;
  }

  if ((millis() - lastPauseBtnMs) > DEBOUNCE_DELAY)
  {
    if (pauseReading != pauseBtnStable)
    {
      pauseBtnStable = pauseReading;

      if (pauseBtnStable == LOW)
      {
        // Button pressed — toggle freeze
        paused = !paused;
        printSerialTelemetry();
      }
    }
  }
}


// =====================================================
// CAPTURE WAVEFORM
// =====================================================

void captureFrame()
{
  if (paused)
    return;


  long targetSampleIntervalUs =
    timeDivPresetsUs[timeDivIndex] / 16;


  long delayUs =
    targetSampleIntervalUs - 4;


  if (delayUs < 0)
    delayUs = 0;


  uint16_t minAdc = 1023;
  uint16_t maxAdc = 0;

  uint32_t sumAdcSquared = 0;


  unsigned long startTime = micros();


  for (uint8_t i = 0; i < BUF_LEN; i++)
  {
    uint16_t raw =
      analogRead(PIN_SCOPE_INPUT);


    sampleBuf[i] =
      raw >> 2;


    if (raw < minAdc)
      minAdc = raw;


    if (raw > maxAdc)
      maxAdc = raw;


    sumAdcSquared +=
      (uint32_t)raw * raw;


    if (delayUs > 0)
      delayMicroseconds(delayUs);

    // Poll the inputs inside the capture loop periodically to avoid lag
    if (i % 16 == 0)
    {
      handleInputs();
    }
  }


  unsigned long totalTimeUs =
    micros() - startTime;


  float actualSampleRateUs =
    (float)totalTimeUs / BUF_LEN;


  // ----------------------------------
  // Voltage measurements
  // ----------------------------------

  signalVpp =
    (maxAdc - minAdc)
    * ADC_TO_VIN;


  float meanSquareAdc =
    (float)sumAdcSquared / BUF_LEN;


  signalVrms =
    sqrt(meanSquareAdc)
    * ADC_TO_VIN;


  // ----------------------------------
  // Frequency Detection
  // ----------------------------------

  uint8_t minVal =
    minAdc >> 2;

  uint8_t maxVal =
    maxAdc >> 2;


  float midAdc =
    minVal +
    ((maxVal - minVal) / 2.0);


  float firstCross = -1.0;
  float lastCross = -1.0;

  uint8_t edgesFound = 0;


  for (
    uint8_t i = 0;
    i < BUF_LEN - 1;
    i++
  )
  {
    if (
      sampleBuf[i] < midAdc &&
      sampleBuf[i + 1] >= midAdc
    )
    {
      float dy =
        (float)(
          sampleBuf[i + 1] -
          sampleBuf[i]
        );


      float exactCross;

      if (dy > 0)
      {
        exactCross =
          (float)i +
          (
            midAdc -
            sampleBuf[i]
          )
          / dy;
      }
      else
      {
        exactCross = i;
      }


      if (firstCross < 0)
      {
        firstCross =
          exactCross;
      }


      lastCross =
        exactCross;


      edgesFound++;
    }
  }


  if (
    edgesFound >= 2 &&
    signalVpp > 0.4
  )
  {
    float totalCycles =
      edgesFound - 1;


    float avgPeriodSamples =
      (lastCross - firstCross)
      / totalCycles;


    float periodSec =
      (
        avgPeriodSamples *
        actualSampleRateUs
      )
      / 1000000.0;


    if (periodSec > 0)
    {
      signalFreq =
        1.0 / periodSec;
    }
    else
    {
      signalFreq = 0;
    }
  }
  else
  {
    signalFreq = 0;
  }
}


// =====================================================
// CANVAS RENDERING UTILITIES
// =====================================================

void setCanvasPixel(int x, int y, uint8_t colorIdx)
{
  if (x < 0 || x >= GRAPH_W || y < 0 || y >= GRAPH_H) return;
  int pixelIndex = y * GRAPH_W + x;
  int byteIndex = pixelIndex / 4;
  int shift = (3 - (pixelIndex % 4)) * 2;
  canvas[byteIndex] = (canvas[byteIndex] & ~(0b11 << shift)) | (colorIdx << shift);
}

void drawCanvasLine(int x0, int y0, int x1, int y1, uint8_t colorIdx)
{
  int dx = abs(x1 - x0), sx = x0 < x1 ? 1 : -1;
  int dy = -abs(y1 - y0), sy = y0 < y1 ? 1 : -1;
  int err = dx + dy, e2;
  
  while (true) {
    setCanvasPixel(x0, y0, colorIdx);
    if (x0 == x1 && y0 == y1) break;
    e2 = 2 * err;
    if (e2 >= dy) { err += dy; x0 += sx; }
    if (e2 <= dx) { err += dx; y0 += sy; }
  }
}

void drawGridOnCanvas()
{
  // Draw border (color 3 = COLOR_WHITE)
  for (int x = 0; x < GRAPH_W; x++) {
    setCanvasPixel(x, 0, 3);
    setCanvasPixel(x, GRAPH_H - 1, 3);
  }
  for (int y = 0; y < GRAPH_H; y++) {
    setCanvasPixel(0, y, 3);
    setCanvasPixel(GRAPH_W - 1, y, 3);
  }

  // Vertical divisions (color 1 = COLOR_DARKGREY)
  for (int x = 20; x < GRAPH_W; x += 20)
  {
    for (int y = 2; y < GRAPH_H; y += 4)
    {
      setCanvasPixel(x, y, 1);
    }
  }

  // Horizontal divisions (color 1 = COLOR_DARKGREY)
  for (int y = 20; y < GRAPH_H; y += 20)
  {
    for (int x = 2; x < GRAPH_W; x += 4)
    {
      setCanvasPixel(x, y, 1);
    }
  }

  // Center vertical line
  int centerX = GRAPH_W / 2;
  for (int y = 1; y < GRAPH_H - 1; y++)
  {
    setCanvasPixel(centerX, y, 1);
  }

  // Center horizontal line
  int centerY = GRAPH_H / 2;
  for (int x = 1; x < GRAPH_W - 1; x++)
  {
    setCanvasPixel(x, centerY, 1);
  }
}

void drawWaveformOnCanvas()
{
  float voltsPerDiv = voltsDivPresets[voltsDivIndex];
  
  // Base zero coordinate local to canvas
  int baseZeroY = GRAPH_H / 2 + yOffset;
  baseZeroY = constrain(baseZeroY, 2, GRAPH_H - 3);

  int prevX = -1;
  int prevY = 0;

  for (uint8_t i = 0; i < BUF_LEN; i++)
  {
    int rawAdc = sampleBuf[i] << 2;
    float vin = rawAdc * ADC_TO_VIN;

    // 20 pixels = 1 division
    int y = baseZeroY - (int)((vin / voltsPerDiv) * 20.0);
    y = constrain(y, 1, GRAPH_H - 2);

    int x = map(i, 0, BUF_LEN - 1, 0, GRAPH_W - 1) + xOffset;
    x = constrain(x, 1, GRAPH_W - 2);

    if (prevX >= 0)
    {
      drawCanvasLine(prevX, prevY, x, y, 2); // 2 = COLOR_GREEN
    }

    prevX = x;
    prevY = y;
  }
}


// =====================================================
// DRAW STATIC UI
// =====================================================

void drawStaticUI()
{
  tft.setFont(
    Terminal6x8
  );

  tft.drawText(
    5,
    5,
    "MINI OSCILLOSCOPE",
    COLOR_YELLOW
  );

  tft.drawLine(
    0,
    28,
    SCREEN_W,
    28,
    COLOR_WHITE
  );
}


// =====================================================
// DRAW HEADER
// =====================================================

void drawHeader()
{
  tft.setFont(
    Terminal6x8
  );

  char buffer[32];

  // VPP
  sprintf(
    buffer,
    "VPP:%-6.2fV",
    signalVpp
  );

  tft.drawText(
    5,
    17,
    buffer,
    COLOR_WHITE
  );

  // VRMS
  sprintf(
    buffer,
    "RMS:%-6.2fV",
    signalVrms
  );

#if IS_LANDSCAPE
  tft.drawText(
    75,
    17,
    buffer,
    COLOR_WHITE
  );
#else
  tft.drawText(
    65,
    17,
    buffer,
    COLOR_WHITE
  );
#endif

  // Frequency
  char freqBuf[16];
  if (signalFreq >= 1000)
  {
    sprintf(
      freqBuf,
      "%.1fkHz",
      signalFreq / 1000.0
    );
  }
  else
  {
    sprintf(
      freqBuf,
      "%.0fHz",
      signalFreq
    );
  }
  sprintf(buffer, "%-8s", freqBuf);

#if IS_LANDSCAPE
  tft.drawText(
    155,
    17,
    buffer,
    COLOR_CYAN
  );
#else
  tft.drawText(
    125,
    17,
    buffer,
    COLOR_CYAN
  );
#endif
}


// =====================================================
// DRAW STATUS BUTTON
// =====================================================

void drawStatusBox(
  int x,
  int y,
  int w,
  int h,
  bool selected,
  const char *text
)
{
  uint16_t borderColor =
    selected ?
    COLOR_YELLOW :
    COLOR_WHITE;

  uint16_t fillColor =
    selected ?
    COLOR_BLUE :
    COLOR_BLACK;


  tft.drawRectangle(
    x,
    y,
    x + w,
    y + h,
    borderColor
  );


  tft.fillRectangle(
    x + 1,
    y + 1,
    x + w - 1,
    y + h - 1,
    fillColor
  );


  tft.drawText(
    x + 3,
    y + 4,
    text,
    selected ?
    COLOR_WHITE :
    COLOR_CYAN
  );
}


// =====================================================
// DRAW SETTINGS BOX (GEAR ICON)
// =====================================================

void drawSettingsBox(
  int x,
  int y,
  int w,
  int h,
  bool selected
)
{
  uint16_t borderColor =
    selected ?
    COLOR_YELLOW :
    COLOR_WHITE;

  uint16_t fillColor =
    selected ?
    COLOR_BLUE :
    COLOR_BLACK;

  tft.drawRectangle(
    x,
    y,
    x + w,
    y + h,
    borderColor
  );

  tft.fillRectangle(
    x + 1,
    y + 1,
    x + w - 1,
    y + h - 1,
    fillColor
  );

  int cx = x + w / 2;
  int cy = y + h / 2;
  uint16_t iconColor = selected ? COLOR_WHITE : COLOR_CYAN;

  // Draw gear spokes
  tft.drawLine(cx - 5, cy, cx + 5, cy, iconColor);
  tft.drawLine(cx, cy - 5, cx, cy + 5, iconColor);
  tft.drawLine(cx - 3, cy - 3, cx + 3, cy + 3, iconColor);
  tft.drawLine(cx - 3, cy + 3, cx + 3, cy - 3, iconColor);

  // Outer gear body
  tft.drawCircle(cx, cy, 3, iconColor);

  // Hollow center
  tft.fillCircle(cx, cy, 2, fillColor);
}


// =====================================================
// DRAW FREEZE STATUS BOX
// =====================================================

void drawFreezeBox(
  int x,
  int y,
  int w,
  int h,
  bool selected,
  bool frozen
)
{
  uint16_t borderColor =
    selected ? COLOR_YELLOW : COLOR_WHITE;

  uint16_t fillColor =
    selected ? COLOR_BLUE : COLOR_BLACK;

  uint16_t textColor;
  if (selected)
    textColor = COLOR_WHITE;
  else
    textColor = frozen ? COLOR_RED : COLOR_GREEN;

  tft.drawRectangle(
    x, y, x + w, y + h,
    borderColor
  );

  tft.fillRectangle(
    x + 1, y + 1, x + w - 1, y + h - 1,
    fillColor
  );

  tft.drawText(
    x + 3, y + 4,
    frozen ? "FROZEN  " : "RUNNING ",
    textColor
  );
}


// =====================================================
// DRAW STATUS BAR
// =====================================================

void drawStatusBar()
{
  char buffer[20];


  tft.setFont(
    Terminal6x8
  );


  // -------------------------
  // Volts / Div
  // -------------------------

  sprintf(
    buffer,
    "%.1fV",
    voltsDivPresets[voltsDivIndex]
  );


#if IS_LANDSCAPE
  drawStatusBox(
    5,
    STATUS_Y,
    48,
    16,
    currentMode == VOLTS_DIV,
    buffer
  );
#else
  drawStatusBox(
    5,
    STATUS_Y,
    48,
    18,
    currentMode == VOLTS_DIV,
    buffer
  );
#endif


  // -------------------------
  // Time / Div
  // -------------------------

  if (
    timeDivPresetsUs[timeDivIndex] >= 1000
  )
  {
    sprintf(
      buffer,
      "%dms",
      timeDivPresetsUs[timeDivIndex] / 1000
    );
  }
  else
  {
    sprintf(
      buffer,
      "%dus",
      timeDivPresetsUs[timeDivIndex]
    );
  }


#if IS_LANDSCAPE
  drawStatusBox(
    58,
    STATUS_Y,
    50,
    16,
    currentMode == TIME_DIV,
    buffer
  );
#else
  drawStatusBox(
    60,
    STATUS_Y,
    50,
    18,
    currentMode == TIME_DIV,
    buffer
  );
#endif


  // -------------------------
  // X Position
  // -------------------------

  sprintf(
    buffer,
    "X:%d",
    xOffset
  );


#if IS_LANDSCAPE
  drawStatusBox(
    113,
    STATUS_Y,
    48,
    16,
    currentMode == X_POS,
    buffer
  );
#else
  drawStatusBox(
    117,
    STATUS_Y,
    52,
    18,
    currentMode == X_POS,
    buffer
  );
#endif


  // -------------------------
  // Y Position
  // -------------------------

  sprintf(
    buffer,
    "Y:%d",
    yOffset
  );


#if IS_LANDSCAPE
  drawStatusBox(
    166,
    STATUS_Y,
    48,
    16,
    currentMode == Y_POS,
    buffer
  );
#else
  drawStatusBox(
    5,
    198,
    55,
    18,
    currentMode == Y_POS,
    buffer
  );
#endif


  // -------------------------
  // Settings Icon Box
  // -------------------------

#if IS_LANDSCAPE
  drawSettingsBox(
    5,
    STATUS_Y + 20,
    24,
    16,
    currentMode == SETTINGS
  );
#else
  drawSettingsBox(
    140,
    198,
    31,
    18,
    currentMode == SETTINGS
  );
#endif


  // -------------------------
  // Freeze Status Box
  // (selectable via encoder — turn to toggle)
  // -------------------------

#if IS_LANDSCAPE
  drawFreezeBox(
    34,
    STATUS_Y + 20,
    80,
    16,
    currentMode == FREEZE,
    paused
  );
#else
  drawFreezeBox(
    63,
    198,
    68,
    18,
    currentMode == FREEZE,
    paused
  );
#endif
}


void drawUI(bool forceRedraw)
{
  // 1. Clear the canvas to black (color index 0)
  memset(canvas, 0, sizeof(canvas));

  // 2. Draw grid and border on canvas
  drawGridOnCanvas();

  // 3. Draw waveform on canvas
  drawWaveformOnCanvas();

  // 4. Push the canvas to the display at GRAPH_X, GRAPH_Y
  tft.draw2BitBitmap(
    GRAPH_X,
    GRAPH_Y,
    canvas,
    GRAPH_W,
    GRAPH_H,
    COLOR_BLACK,
    COLOR_DARKGREY,
    COLOR_GREEN,
    COLOR_WHITE
  );

  // 5. Update header and status bar
  static unsigned long lastTextUpdateMs = 0;
  if (forceRedraw || (millis() - lastTextUpdateMs >= 300))
  {
    drawHeader();
    drawStatusBar();
    lastTextUpdateMs = millis();
  }
}


// =====================================================
// SETUP
// =====================================================

void setup()
{
  Serial.begin(9600);

  delay(200);


  // -------------------------
  // Input pins
  // -------------------------

  pinMode(
    PIN_ENC_CLK,
    INPUT_PULLUP
  );

  pinMode(
    PIN_ENC_DT,
    INPUT_PULLUP
  );

  pinMode(
    PIN_ENC_SW,
    INPUT_PULLUP
  );

  pinMode(
    PIN_PAUSE_BTN,
    INPUT_PULLUP
  );


  // -------------------------
  // ADC
  // -------------------------

  analogReadResolution(10);


  // -------------------------
  // Encoder interrupts
  // -------------------------

  attachInterrupt(
    digitalPinToInterrupt(
      PIN_ENC_CLK
    ),
    encoderISR,
    CHANGE
  );

  attachInterrupt(
    digitalPinToInterrupt(
      PIN_ENC_DT
    ),
    encoderISR,
    CHANGE
  );


  // -------------------------
  // Initialize TFT
  // -------------------------

  tft.begin();

  tft.setOrientation(displayRotation);

  tft.setBackgroundColor(
    COLOR_BLACK
  );

  tft.clear();

  drawStaticUI();


  Serial.println(
    F("--- UNO R4 MINIMA TFT OSCILLOSCOPE READY ---")
  );


  printSerialTelemetry();
}


// =====================================================
// MAIN LOOP
// =====================================================

void loop()
{
  handleInputs();

  captureFrame();

  // Check if parameters changed, or if 70ms has passed since last redraw
  static int8_t lastVoltsDivIndex = -1;
  static int8_t lastTimeDivIndex = -1;
  static int8_t lastXOffset = 99;
  static int8_t lastYOffset = 99;
  static uint8_t lastCurrentMode = 99;
  static bool lastPaused = false;

  bool parameterChanged = (voltsDivIndex != lastVoltsDivIndex ||
                           timeDivIndex != lastTimeDivIndex ||
                           xOffset != lastXOffset ||
                           yOffset != lastYOffset ||
                           currentMode != lastCurrentMode ||
                           paused != lastPaused);

  unsigned long now = millis();

  if (parameterChanged || (!paused && (now - lastRedrawMs >= 70)))
  {
    drawUI(parameterChanged);
    lastRedrawMs = now;

    lastVoltsDivIndex = voltsDivIndex;
    lastTimeDivIndex = timeDivIndex;
    lastXOffset = xOffset;
    lastYOffset = yOffset;
    lastCurrentMode = currentMode;
    lastPaused = paused;
  }


  // Serial telemetry

  if (
    millis() -
    lastSerialPrintMs >=
    1000
  )
  {
    printSerialTelemetry();

    lastSerialPrintMs =
      millis();
  }
}