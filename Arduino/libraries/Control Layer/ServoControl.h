#ifndef SERVO_CONTROL_H
#define SERVO_CONTROL_H

#include <Arduino.h>
#include <Wire.h>
#include <Adafruit_PWMServoDriver.h>

// ─── Configuration ────────────────────────────────────────────────────────────

// Maximum number of daisy-chained PCA9685 boards
#define MAX_BOARDS    2

// Maximum number of logical servos across all boards
#define MAX_SERVOS   18

// PWM pulse width range (microseconds)
#define PWM_MIN_MICROSEC  400   // Minimum pulse
#define PWM_MAX_MICROSEC 2600   // Maximum pulse

// Servo angle range (degrees)
#define MAX_SERVO_ANGLE  180

// PCA9685 PWM frequency (Hz)
#define PWM_FREQUENCY     60

// ─── Externally visible data structures ──────────────────────────────────────

// One Adafruit driver instance per board
extern Adafruit_PWMServoDriver pwmBoards[MAX_BOARDS];

// Number of boards initialised
extern int numBoards;

// Mapping from logical servo index → board index (0…numBoards-1)
extern int servoBoard[MAX_SERVOS];

// Mapping from logical servo index → channel on its board (0…15)
extern int servoChannel[MAX_SERVOS];

// ─── Public API ────────────────────────────────────────────────────────────────

/**
 * @brief Initialise all PCA9685 boards.
 * @param i2cAddrs Array of I2C addresses (e.g. {0x40, 0x41})
 * @param count    Number of addresses in the array (≤ MAX_BOARDS)
 *
 * Must be called once in setup() before any mapping or angle commands.
 */
void setupServoDrivers(const uint8_t i2cAddrs[], int count);

/**
 * @brief Define which board and channel a logical servo uses.
 * @param servoIndex  Logical index (0…MAX_SERVOS−1)
 * @param boardIndex  Which PCA9685 (0…numBoards−1)
 * @param channel     Which PWM channel (0…15) on that board
 */
void setServoMapping(int servoIndex, int boardIndex, int channel);

/**
 * @brief Move a logical servo to a given angle.
 * @param servoIndex  Logical index (0…MAX_SERVOS−1)
 * @param angle       Desired angle (0…MAX_SERVO_ANGLE)
 */
void setServoAngle(int servoIndex, int angle);

/**
 * @brief Convert angle to pulse count (for debugging and verification).
 * @param angle       Desired angle (0…MAX_SERVO_ANGLE)
 * @return           Pulse width value sent to the PCA9685
 */
int angleToPulse(int angle);

#endif  // SERVO_CONTROL_H
