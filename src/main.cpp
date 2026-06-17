#include <MD_MAX72xx.h>
#include <SPI.h>

// config
#define HARDWARE_TYPE MD_MAX72XX::FC16_HW
#define MAX_DEVICES 14

// pins
#define BUTTON_PIN 7
#define CLK_PIN   13
#define DATA_PIN  11
#define CS_PIN    12

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

// reaction vars
bool animatingMouth = false;
uint8_t mouthStep = 0;
unsigned long lastMouthAnim = 0;

// reaction sequence state vars
uint8_t reactionPhase = 0;
unsigned long reactionTimer = 0;
uint8_t mouthCycleCount = 0;

// button detection vars
int buttonIdleState = HIGH;
const unsigned long DEBOUNCE_MS = 50;
int lastRawButton = HIGH;
unsigned long lastDebounceTime = 0;
bool debouncedPressed = false;

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

      uint16_t globalCol = device * 8 + x;
      M.setPoint(y, globalCol, pixel);
    }
  }
}

// eyes
void displayEyes()
{
  M.update(MD_MAX72XX::OFF);
  drawModule(EYE_L_START + 0, E1, FLIP_180);
  drawModule(EYE_L_START + 1, E2, FLIP_180);
  drawModule(EYE_R_START + 0, E2, FLIP_Y);
  drawModule(EYE_R_START + 1, E1, FLIP_Y);
  M.update();
}

// nose
void displayNose()
{
  M.update(MD_MAX72XX::OFF);
  drawModule(NOSE_L, N1, FLIP_180);
  drawModule(NOSE_R, N1, FLIP_Y);
  M.update();
}

// mouth static
void displayMouth()
{
  M.update(MD_MAX72XX::OFF);
  drawModule(MOUTH_L_START + 0, M4, 0);
  drawModule(MOUTH_L_START + 1, M3, 0);
  drawModule(MOUTH_L_START + 2, M2, 0);
  drawModule(MOUTH_L_START + 3, M1, 0);

  drawModule(MOUTH_R_START + 0, M1, FLIP_X);
  drawModule(MOUTH_R_START + 1, M2, FLIP_X);
  drawModule(MOUTH_R_START + 2, M3, FLIP_X);
  drawModule(MOUTH_R_START + 3, M4, FLIP_X);
  M.update();
}

// mouth animation
void displayMouthAnimated(uint8_t step)
{
  M.update(MD_MAX72XX::OFF);
  drawModule(MOUTH_L_START + 0,  M4, 0);
  drawModule(MOUTH_L_START + 1,  M3, 0);
  drawModule(MOUTH_L_START + 2,  M2, 0);
  drawModule(MOUTH_L_START + 3,  M1, 0);

  drawModule(MOUTH_R_START + 0, M1, FLIP_X);
  drawModule(MOUTH_R_START + 1, M2, FLIP_X);
  drawModule(MOUTH_R_START + 2, M3, FLIP_X);
  drawModule(MOUTH_R_START + 3, M4, FLIP_X);

  if (step > 0) M.clear(MOUTH_L_START + 3);
  if (step > 1) M.clear(MOUTH_L_START + 2);
  if (step > 2) M.clear(MOUTH_L_START + 1);

  if (step > 2) M.clear(MOUTH_R_START + 2);
  if (step > 1) M.clear(MOUTH_R_START + 1);
  if (step > 0) M.clear(MOUTH_R_START + 0);
  M.update();
}

// blink
void drawBlink()
{
  M.update(MD_MAX72XX::OFF);
  drawModule(EYE_L_START + 0, Blink1, FLIP_180);
  drawModule(EYE_L_START + 1, Blink2, FLIP_180);
  drawModule(EYE_R_START + 0, Blink2, FLIP_Y);
  drawModule(EYE_R_START + 1, Blink1, FLIP_Y);
  M.update();
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

  unsigned long now = millis();

  switch (reactionPhase)
  {
    case 0:
      drawBlink();
      reactionPhase = 1;
      mouthStep = 0;
      mouthCycleCount = 0;
      lastMouthAnim = now;
      break;

    case 1:
      if (now - lastMouthAnim > 20)
      {
        lastMouthAnim = now;
        if (mouthStep < 4)
        {
          mouthStep++;
          displayMouthAnimated(mouthStep);
        }
        else
        {
          reactionPhase = 2;
          reactionTimer = now;
        }
      }
      break;

    case 2:
      if (now - reactionTimer < 150) {}
      break;
  }
}

// button
void checkButton()
{
  int raw = digitalRead(BUTTON_PIN);
  bool pressedRaw = (raw != buttonIdleState);

  if (raw != lastRawButton)
  {
    lastDebounceTime = millis();
    lastRawButton = raw;
  }

  if ((millis() - lastDebounceTime) > DEBOUNCE_MS)
  {
    if (debouncedPressed != pressedRaw)
    {
      debouncedPressed = pressedRaw;

      if (debouncedPressed)
      {
        // button pressed
        faceState = REACT;
        animatingMouth = true;
        reactionPhase = 0;
        mouthStep = 0;
        mouthCycleCount = 0;
        lastMouthAnim = millis();
        drawBlink();
      }
      else
      {
        // button released
        animatingMouth = false;
        faceState = IDLE;
        mouthStep = 0;
        reactionPhase = 0;
        displayMouth();
        displayEyes();
        displayNose();
      }
    }
  }
}

// setup
void setup()
{
  M.begin();
  M.control(MD_MAX72XX::INTENSITY, 1);
  M.clear();

  pinMode(BUTTON_PIN, INPUT_PULLUP);

  buttonIdleState = digitalRead(BUTTON_PIN);
  lastRawButton = digitalRead(BUTTON_PIN);
  debouncedPressed = (lastRawButton != buttonIdleState);
  lastDebounceTime = millis();

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