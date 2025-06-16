#include "RemoteControl.h"

// Markers and packet sizes for serial communication between Pi and Arduino.
#define SYNC_MARKER         0xAA  // Marker for sync packet.
#define SYNC_TYPE           0x01  // Expected type value in sync packet.
#define SYNC_PACKET_SIZE    6     // marker(1) + type(1) + startTime(4).

#define COMMAND_MARKER      0xBB  // Marker for pick/strum command packet.
#define COMMAND_PACKET_SIZE 7  // marker(1) + target(1) + angle(1) + delay(4)

#define GET_TIME_MARKER       0xCC  // Marker to request current millis().
#define GET_TIME_PACKET_SIZE  1     // marker(1).

#define END_MARKER        0xDD  // Marker signalling end of song.
#define END_PACKET_SIZE   5     // marker(1) + relativeDelay(4).

#define STOP_MARKER      0xEE  // STOP: clears buffer, disables sync
#define RESET_MARKER     0xEF  // RESET: followed by servo neutral angles
#define MAX_RESET_SERVOS 18    // Number of servos to reset

// Constructor initialises control state without enabling debug or sync.
RemoteControl::RemoteControl()
  : commandCount(0), syncReceived(false),
    syncStartTime(0), debugEnabled(false)
{}

// Initialise servo drivers and optionally enable debug output.
void RemoteControl::begin(const uint8_t i2cAddrs[], int addrCount, bool debug) {
    debugEnabled = debug;
    // Initialise all PCA9685 boards
    setupServoDrivers(i2cAddrs, addrCount);
    if (debugEnabled) {
        Serial.println("RemoteControl: Servo drivers initialised.");
    }
}

// Map a logical servo index to a specific board and channel.
void RemoteControl::addServo(uint8_t boardIndex,
                             uint8_t channel,
                             uint8_t servoIndex) {
    setServoMapping(servoIndex, boardIndex, channel);
    if (debugEnabled) {
        Serial.print("RemoteControl: Mapped servo ");
        Serial.print(servoIndex);
        Serial.print(" → board ");
        Serial.print(boardIndex);
        Serial.print(", channel ");
        Serial.println(channel);
    }
}

// Main loop entry point to process incoming data and execute pending commands.
void RemoteControl::handle() {
    parseSerialData();  // Interpret and buffer any serial packets available.
    update();           // Perform any commands whose time has arrived.
}


// Parse incoming serial packets and buffer commands accordingly.
void RemoteControl::parseSerialData() {
    while (Serial.available() > 0) {
        int avail  = Serial.available();  // Number of bytes currently in buffer.
        int marker = Serial.peek();       // Inspect next byte without consuming it.
            // —— STOP packet ——
        if (marker == STOP_MARKER && avail >= 1) {
            Serial.read();  // consume 0xEE
            commandCount = 0;
            syncReceived = false;
            Serial.println("STOPPED");
            continue;  // Immediate priority: skip further checks.
        }

        // —— RESET packet ——
        else if (marker == RESET_MARKER && avail >= (1 + MAX_RESET_SERVOS * 2)) {
            Serial.read(); // consume 0xEF
            for (int idx = 0; idx < MAX_RESET_SERVOS; ++idx) {
                int hi = Serial.read();
                int lo = Serial.read();
                int16_t angle = (int16_t)((hi << 8) | lo);
                setServoAngle(idx, angle);  // Move servo to neutral
            }
            if (debugEnabled) Serial.println("RemoteControl: Servos RESET to dynamic angles.");
            Serial.println("RESET_DONE");
            continue;  // High priority: skip other checks.
    }

        /// —— PICK command packet ——
        if (marker == COMMAND_MARKER && avail >= COMMAND_PACKET_SIZE) {
            Serial.read();                    // Discard command marker.
            Command cmd;
            cmd.targetIndex   = Serial.read();    // 1 byte: servo index
            cmd.angle         = Serial.read();    // 1 byte: angle in degrees (0-180)
            // 4 bytes: delay (little-endian)
            uint32_t d0 = Serial.read();
            uint32_t d1 = Serial.read();
            uint32_t d2 = Serial.read();
            uint32_t d3 = Serial.read();
            cmd.relativeDelay = d0 | (d1 << 8) | (d2 << 16) | (d3 << 24);

            if (commandCount < MAX_COMMANDS) {
                commandBuffer[commandCount++] = cmd;  // Buffer the pick command.
                if (debugEnabled) {
                    Serial.print("RemoteControl: Buffered PICK T=");
                    Serial.print(cmd.targetIndex);
                    Serial.print(" A=");
                    Serial.print(cmd.angle);
                    Serial.print(" D=");
                    Serial.print(cmd.relativeDelay);
                    Serial.println("ms");  // Report buffered command.
                }
            } else {
                Serial.println("ERROR: command buffer full");
            }
            continue;
        }

        // —— END‐OF‐SONG packet —— 
        else if (marker == END_MARKER && avail >= END_PACKET_SIZE) {
            Serial.read();  // consume the 0xDD
            // read 32‐bit relative delay (little-endian, like pick commands)
            uint32_t d0 = Serial.read();
            uint32_t d1 = Serial.read();
            uint32_t d2 = Serial.read();
            uint32_t d3 = Serial.read();
            uint32_t rel = d0 | (d1 << 8) | (d2 << 16) | (d3 << 24);

            // Buffer special command to signal song end (targetIndex=255).
            if (commandCount < MAX_COMMANDS) {
                Command cmd;
                cmd.targetIndex   = 255;      // Special sentinel index.
                cmd.angle         = 0;        // Angle unused for end marker.
                cmd.relativeDelay = rel;      // Delay after sync time.
                commandBuffer[commandCount++] = cmd;  // Add to buffer.
            }
            continue;  // Continue parsing further packets.
        }

        // —— GET_TIME packet ——
        else if (marker == GET_TIME_MARKER && avail >= GET_TIME_PACKET_SIZE) {
            Serial.read();               // Consume the 0xCC marker.
            Serial.print("TIME:");     // Prefix for time reply.
            Serial.println(millis());    // Send current millis() back.
            continue;                    // Process any more packets.
        }

        // —— SYNC packet ——
        else if (marker == SYNC_MARKER && avail >= SYNC_PACKET_SIZE) {
            Serial.read();                     // Discard sync marker.
            int type = Serial.read();         // Read packet type.
            if (type != SYNC_TYPE) {
                errorHandler("Unexpected sync packet type");  // Abort on mismatch.
                return;
            }
            uint32_t t = 0;
            t |= (uint32_t)Serial.read() << 24;  // Assemble startTime MSB.
            t |= (uint32_t)Serial.read() << 16;
            t |= (uint32_t)Serial.read() << 8;
            t |= (uint32_t)Serial.read();       // Assemble LSB.
            syncStartTime = t;                   // Record base time for commands.
            syncReceived  = true;                // Enable command execution.
            commandCount  = 0;                   // Clear any old commands.
            if (debugEnabled) {
                Serial.print("RemoteControl: Sync at ");
                Serial.println(t);               // Log sync timestamp.
            }
            continue;
        }
        else {
            break;  // Incomplete or unrecognised packet at buffer front.
        }
    }
}

// Execute buffered commands whose scheduled time has been reached since sync.
void RemoteControl::update() {
    if (!syncReceived) return;  // Skip if no sync received.

    unsigned long now = millis();  // Get current time reference.
    int i = 0;
    while (i < commandCount) {
        unsigned long execTime = syncStartTime + commandBuffer[i].relativeDelay;
        if (now >= execTime) {
            // is this our end‐of‐song marker?
            if (commandBuffer[i].targetIndex == 255) {
                // print DONE and stop accepting further commands
                Serial.println("DONE");      // Signal end of song.
                syncReceived = false;         // Stop further execution.
            }
            else {
                // execute pick
                if (debugEnabled) {
                    Serial.print("Executing PICK: index=");
                    Serial.print(commandBuffer[i].targetIndex);
                    Serial.print(" angle=");
                    Serial.print(commandBuffer[i].angle);
                    Serial.print(" pulse=");
                    Serial.println(angleToPulse(commandBuffer[i].angle)); // print the pulse
                }
                setServoAngle(commandBuffer[i].targetIndex,
                            commandBuffer[i].angle);  // Trigger servo motion.
            }

            // Remove executed command by shifting buffer left.
            for (int j = i; j < commandCount - 1; j++) {
                commandBuffer[j] = commandBuffer[j + 1];
            }
            --commandCount;  // Reduce count after removal.
        } else {
            ++i;  // Move to next buffered command.
        }
    }
}

// Handle fatal errors by reporting and halting further operation.
void RemoteControl::errorHandler(const char* msg) {
    Serial.print("RemoteControl ERROR: ");
    Serial.println(msg);
    while (true) {
        delay(1000);
        Serial.print("RemoteControl ERROR: ");
        Serial.println(msg);
    }
}
