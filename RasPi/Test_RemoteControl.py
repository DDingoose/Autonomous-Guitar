import serial
import time
import struct

SERIAL_PORT = '/dev/ttyACM0'  # Adjust as needed
BAUD = 9600

GET_TIME_MARKER = 0xCC
SYNC_MARKER     = 0xAA
SYNC_TYPE       = 0x01
COMMAND_MARKER  = 0xBB

servo_indices = [6, 7, 8, 9, 10, 11]
test_angles = [0, 60, 120]
wait_time = 2      # seconds between angle sets (for human observation)
servo_delay_ms = 4000  # time after SYNC to first actuation, in ms
angle_interval_ms = 2000  # ms between each angle change

def get_arduino_time(ser):
    ser.write(bytes([GET_TIME_MARKER]))
    ser.flush()
    line = ser.readline().decode(errors='ignore')
    while not line.startswith('TIME:'):
        line = ser.readline().decode(errors='ignore')
    millis = int(line.strip().split(':')[1])
    print(f"Arduino millis: {millis}")
    return millis

def send_sync(ser, millis):
    sync_packet = struct.pack('>BBI', SYNC_MARKER, SYNC_TYPE, millis)
    ser.write(sync_packet)
    ser.flush()
    print(f"Sent SYNC: {millis}")

def send_command(ser, target, angle, rel_delay=0):
    packet = struct.pack('>BBhh', COMMAND_MARKER, target, angle, rel_delay)
    ser.write(packet)
    ser.flush()

def main():
    print(f"Connecting to Arduino on {SERIAL_PORT} at {BAUD} baud...")
    ser = serial.Serial(SERIAL_PORT, BAUD, timeout=2)
    time.sleep(2)  # Wait for Arduino to boot/reset

    # Step 1: Get Arduino time and send SYNC only once
    arduino_time = get_arduino_time(ser)
    send_sync(ser, arduino_time)
    time.sleep(0.1)

    # Step 2: Buffer all servo commands for all angles, each with increasing relative delay
    for ai, angle in enumerate(test_angles):
        actuation_delay = servo_delay_ms + ai * angle_interval_ms
        print(f"\nBuffering commands to move servos to angle {angle} at SYNC+{actuation_delay} ms")
        for servo in servo_indices:
            send_command(ser, servo, angle, actuation_delay)
            time.sleep(0.1)  # Add delay per command so the Arduino can buffer

if __name__ == "__main__":
    main()
