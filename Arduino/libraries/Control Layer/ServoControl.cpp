#include "ServoControl.h"

// Calculate pulse-length bounds once we know the PWM frequency:
static int servomin;
static int servomax;

// Driver instances for each PCA9685
Adafruit_PWMServoDriver pwmBoards[MAX_BOARDS];

// Number of boards actually set up
int numBoards = 0;

// Mapping tables: logical → physical
int servoBoard[MAX_SERVOS];
int servoChannel[MAX_SERVOS];

/**
 * @brief Initialise multiple PCA9685 boards at given I2C addresses.
 */
void setupServoDrivers(const uint8_t i2cAddrs[], int count) {
    // Determine how many boards we can support
    numBoards = (count < MAX_BOARDS ? count : MAX_BOARDS);

    // Compute servo pulse bounds
    servomin = map(PWM_MIN_MICROSEC,
                   0,
                   1000000 / PWM_FREQUENCY,
                   0,
                   4096);
    servomax = map(PWM_MAX_MICROSEC,
                   0,
                   1000000 / PWM_FREQUENCY,
                   0,
                   4096);

    Wire.begin();

    // Initialise each PCA9685
    for (int i = 0; i < numBoards; i++) {
        pwmBoards[i] = Adafruit_PWMServoDriver(i2cAddrs[i]);
        pwmBoards[i].begin();
        pwmBoards[i].setPWMFreq(PWM_FREQUENCY);
    }

    // Default mapping: servo N → board 0, channel N
    for (int s = 0; s < MAX_SERVOS; s++) {
        servoBoard[s]   = 0;
        servoChannel[s] = (s < 16 ? s : 0);
    }
}

/**
 * @brief Override the default mapping for one servo.
 */
void setServoMapping(int servoIndex, int boardIndex, int channel) {
    if (servoIndex >= 0 && servoIndex < MAX_SERVOS
     && boardIndex  >= 0 && boardIndex  < numBoards
     && channel     >= 0 && channel     < 16) {
        servoBoard[servoIndex]   = boardIndex;
        servoChannel[servoIndex] = channel;
    }
}

/**
 * @brief Convert angle to pulse count.
 */
int angleToPulse(int angle) {
    // Clamp angle
    if (angle < 0) angle = 0;
    if (angle > MAX_SERVO_ANGLE) angle = MAX_SERVO_ANGLE;

    return map(angle, 0, MAX_SERVO_ANGLE, servomin, servomax);
}

/**
 * @brief Move a logical servo to the specified angle.
 */
void setServoAngle(int servoIndex, int angle) {
    if (servoIndex < 0 || servoIndex >= MAX_SERVOS) return;

    int b = servoBoard[servoIndex];
    int c = servoChannel[servoIndex];
    int pulse = angleToPulse(angle);

    // Safety check
    if (b < numBoards && c < 16) {
        pwmBoards[b].setPWM(c, 0, pulse);
    }
}
