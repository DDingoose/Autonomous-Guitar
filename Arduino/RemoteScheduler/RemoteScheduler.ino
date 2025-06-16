#include <Arduino.h>                        // Core Arduino library for Serial and timing.
#include "RemoteControl.h"                  // Provides servo control functionality.

RemoteControl rc;                          // Instantiates the RemoteControl controller.

// Configures serial communication and initialises all servo drivers.
void setup(){
  Serial.begin(115200);                  // Sets up Serial at 115200 baud.
  while (!Serial);                       // Waits for serial connection to be ready.

  // Initialise PCA9685 servo drivers on two I2C addresses.
  const uint8_t addrs[] = { 0x40, 0x41 };  // I2C addresses for servo driver boards.
  rc.begin(addrs, 2, /*debug=*/true);      // Initialises servos with debug logging enabled.
  
  // Map fretting servos for strings 6 to 17 on board 0 channels 0 to 11.
  rc.addServo(0, 0, 6);                  // Map servo index 6 to board 0 channel 0.
  rc.addServo(0, 1, 7);                  // Map servo index 7 to board 0 channel 1.
  rc.addServo(0, 2, 8);                  // Map servo index 8 to board 0 channel 2.
  rc.addServo(0, 3, 9);                  // Map servo index 9 to board 0 channel 3.
  rc.addServo(0, 4, 10);                 // Map servo index 10 to board 0 channel 4.
  rc.addServo(0, 5, 11);                 // Map servo index 11 to board 0 channel 5.
  rc.addServo(0, 6, 12);                 // Map servo index 12 to board 0 channel 6.
  rc.addServo(0, 7, 13);                 // Map servo index 13 to board 0 channel 7.
  rc.addServo(0, 8, 14);                 // Map servo index 14 to board 0 channel 8.
  rc.addServo(0, 9, 15);                 // Map servo index 15 to board 0 channel 9.
  rc.addServo(0, 10, 16);                // Map servo index 16 to board 0 channel 10.
  rc.addServo(0, 11, 17);                // Map servo index 17 to board 0 channel 11.

  // Map picking servos for strings 0 to 5 on board 1 channels 0 to 5.
  rc.addServo(1, 0, 0);                  // Map servo index 0 to board 1 channel 0.
  rc.addServo(1, 1, 1);                  // Map servo index 1 to board 1 channel 1.
  rc.addServo(1, 2, 2);                  // Map servo index 2 to board 1 channel 2.
  rc.addServo(1, 3, 3);                  // Map servo index 3 to board 1 channel 3.
  rc.addServo(1, 4, 4);                  // Map servo index 4 to board 1 channel 4.
  rc.addServo(1, 5, 5);                  // Map servo index 5 to board 1 channel 5.
}

// Main loop handles incoming commands and triggers servo actions.
void loop() {
  rc.handle();                           // Parses serial and executes scheduled commands.
}
