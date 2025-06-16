#ifndef REMOTE_CONTROL_H
#define REMOTE_CONTROL_H

#include <Arduino.h>
#include "ServoControl.h"

/**
 * @brief RemoteControl handles incoming serial “PICK” commands,
 *        buffers them, and executes each servo move at the correct time.
 */
class RemoteControl {
public:
    // maximum number of buffered commands
    static const int MAX_COMMANDS = 1;

    RemoteControl();

    /**
     * @brief Initialise I2C boards and internal state.
     * @param i2cAddrs   Array of PCA9685 I²C addresses (e.g. {0x40,0x41})
     * @param addrCount  Number of entries in i2cAddrs (≤ MAX_BOARDS)
     * @param debug      If true, enable verbose serial logging
     */
    void begin(const uint8_t i2cAddrs[], int addrCount, bool debug=false);

    /**
     * @brief Map a logical servo index to a specific board & channel.
     * @param boardIndex  PCA9685 board (0…numBoards−1)
     * @param channel     channel on that board (0…15)
     * @param servoIndex  logical index (0…MAX_SERVOS−1)
     */
    void addServo(uint8_t boardIndex, uint8_t channel, uint8_t servoIndex);

    /**
     * @brief Call once per loop to process incoming data and execute due picks.
     */
    void handle();

private:
    // internal representation of one PICK command
    struct Command {
        uint8_t  targetIndex;     // 1 byte: servo index
        uint8_t  angle;           // 1 byte: angle in degrees (0–180)
        uint32_t relativeDelay;   // 4 bytes: delay in ms from sync (0–~49 days)
    };                            // Total: 6 bytes

    void processSerialCommands();
    void parseSerialData();
    void update();  
    void errorHandler(const char* msg);

    Command      commandBuffer[MAX_COMMANDS];
    int          commandCount;
    bool         syncReceived;
    unsigned long syncStartTime;
    bool         debugEnabled;
};

#endif  // REMOTE_CONTROL_H
