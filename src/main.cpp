#include <MD_MAX72xx.h>
#include <SPI.h>

// config
#define HARDWARE_TYPE MD_MAX72XX::FC16_HW
#define MAX_DEVICES 14

// pins
#define BUTTON_PIN 7
#define CLK_PIN   4
#define DATA_PIN  2
#define CS_PIN    3

MD_MAX72XX M = MD_MAX72XX(HARDWARE_TYPE, DATA_PIN, CLK_PIN, CS_PIN, MAX_DEVICES);

// face layout
#define MOUTH_L_START 0
#define EYE_L_START   4
#define NOSE_L        6
#define NOSE_R        7
#define EYE_R_START   8
#define MOUTH_R_START 10

// transforms
#define FLIP_X   1
#define FLIP_Y   2
#define FLIP_180 (FLIP_X | FLIP_Y)

// state
enum FaceState { IDLE, BLINK, REACT };
FaceState faceState = IDLE;

// timing
unsigned long nextBlinkTime = 0;
unsigned long blinkStartTime = 0;
bool isBlinking = false;

// reaction
bool animatingMouth = false;
uint8_t mouthStep = 0;
unsigned long lastMouthAnim = 0;

// blink graphics
const byte Blink1[8] = {
  0b00000000,
  0b11000000,
  0b11111000,
  0b11111100,
  0b00001110,
  0b00000110,
  0b00000000,
  0b00000000
};

const byte Blink2[8] = {
  0b00000000,
  0b00000000,
  0b00000111,
  0b00111111,
  0b11100000,
  0b10000000,
  0b00000000,
  0b00000000
};

// mouth graphics
const byte M1[8] = {
  0b00000100,
  0b00011110,
  0b01111000,
  0b11100000,
  0b10000000,
  0b00000000,
  0b00000000,
  0b00000000
};

const byte M2[8] = {
  0b00000000,
  0b00000000,
  0b00000000,
  0b00000001,
  0b00000111,
  0b00011110,
  0b01111000,
  0b11100000
};

const byte M3[8] = {
  0b00000000,
  0b00000000,
  0b00000000,
  0b00000000,
  0b11100000,
  0b01111000,
  0b00011110,
  0b00000111
};

const byte M4[8] = {
  0b00000000,
  0b00000000,
  0b00000000,
  0b00000111,
  0b00011111,
  0b01111000,
  0b11100000,
  0b10000000
};

// nose graphics
const byte N1[8] = {
  0b01111000,
  0b11110000,
  0b11000000,
  0b11000000,
  0b11000000,
  0b11000000,
  0b10000000,
  0b00000000
};

// eye graphics
const byte E1[8] = {
  0b11110000,
  0b11111100,
  0b11111110,
  0b11111111,
  0b00001111,
  0b00000110,
  0b00000000,
  0b00000000
};

const byte E2[8] = {
  0b00000000,
  0b00000111,
  0b00011111,
  0b01111111,
  0b11100000,
  0b10000000,
  0b00000000,
  0b00000000
};

// draw module
void drawModule(uint8_t device, const byte data[8], uint8_t mode)
{
  for (uint8_t r = 0; r < 8; r++)
  {
    for (uint8_t c = 0; c < 8; c++)
    {
      bool pixel = data[r] & (1 << (7 - c));

      uint8_t x = c;
      uint8_t y = r;

      if (mode == FLIP_180)
      {
        x = 7 - x;
        y = 7 - y;
      }
      else
      {
        if (mode & FLIP_X) x = 7 - x;
        if (mode & FLIP_Y) y = 7 - y;
      }

      M.setPoint(y, x, pixel);
    }
  }
}

// eyes
void displayEyes()
{
  drawModule(EYE_L_START + 0, E1, FLIP_Y);
  drawModule(EYE_L_START + 1, E2, FLIP_Y);
  drawModule(EYE_R_START + 0, E1, FLIP_180);
  drawModule(EYE_R_START + 1, E2, FLIP_180);
}

// nose
void displayNose()
{
  drawModule(NOSE_L, N1, FLIP_Y);
  drawModule(NOSE_R, N1, FLIP_180);
}

// mouth static
void displayMouth()
{
  drawModule(MOUTH_L_START + 0, M1, FLIP_X);
  drawModule(MOUTH_L_START + 1, M2, FLIP_X);
  drawModule(MOUTH_L_START + 2, M3, FLIP_X);
  drawModule(MOUTH_L_START + 3, M4, FLIP_X);

  drawModule(MOUTH_R_START + 0, M1, 0);
  drawModule(MOUTH_R_START + 1, M2, 0);
  drawModule(MOUTH_R_START + 2, M3, 0);
  drawModule(MOUTH_R_START + 3, M4, 0);
}

// mouth animation
void displayMouthAnimated(uint8_t step)
{
  drawModule(0,  M1, FLIP_X);
  drawModule(1,  M2, FLIP_X);
  drawModule(2,  M3, FLIP_X);
  drawModule(3,  M4, FLIP_X);

  drawModule(10, M1, 0);
  drawModule(11, M2, 0);
  drawModule(12, M3, 0);
  drawModule(13, M4, 0);

  if (step > 0) M.clear(3);
  if (step > 1) M.clear(2);
  if (step > 2) M.clear(1);
  if (step > 3) M.clear(0);

  if (step > 3) M.clear(10);
  if (step > 2) M.clear(11);
  if (step > 1) M.clear(12);
  if (step > 0) M.clear(13);
}

// blink
void drawBlink()
{
  drawModule(EYE_L_START + 0, Blink1, FLIP_Y);
  drawModule(EYE_L_START + 1, Blink2, FLIP_Y);
  drawModule(EYE_R_START + 0, Blink1, FLIP_180);
  drawModule(EYE_R_START + 1, Blink2, FLIP_180);
}

// idle update
void updateIdle()
{
  if (millis() >= nextBlinkTime)
  {
    faceState = BLINK;
    blinkStartTime = millis();
    isBlinking = true;
  }
}

// blink update
void updateBlink()
{
  if (!isBlinking) return;

  drawBlink();

  if (millis() - blinkStartTime > 150)
  {
    isBlinking = false;
    displayEyes();
    displayMouth();
    displayNose();

    faceState = IDLE;
    nextBlinkTime = millis() + random(5000, 10000);
  }
}

// reaction update
void updateReaction()
{
  if (!animatingMouth) return;

  if (millis() - lastMouthAnim > 120)
  {
    lastMouthAnim = millis();

    if (mouthStep < 4)
    {
      mouthStep++;
      displayMouthAnimated(mouthStep);
    }
    else
    {
      animatingMouth = false;
      faceState = IDLE;
    }
  }
}

// button
void checkButton()
{
  static bool last = HIGH;
  bool now = digitalRead(BUTTON_PIN);

  if (last == HIGH && now == LOW)
  {
    faceState = REACT;

    animatingMouth = true;
    mouthStep = 0;
    lastMouthAnim = millis();

    displayMouthAnimated(0);
    drawBlink();
  }

  last = now;
}

// setup
void setup()
{
  M.begin();
  M.control(MD_MAX72XX::INTENSITY, 5);
  M.clear();

  pinMode(BUTTON_PIN, INPUT_PULLUP);

  randomSeed(analogRead(0));

  displayEyes();
  displayMouth();
  displayNose();

  nextBlinkTime = millis() + random(5000, 10000);
}

// loop
void loop()
{
  checkButton();

  switch (faceState)
  {
    case IDLE: updateIdle(); break;
    case BLINK: updateBlink(); break;
    case REACT: updateReaction(); break;
  }
}