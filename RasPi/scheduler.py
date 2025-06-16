
#!/usr/bin/env python3
"""
scheduler.py


All serial and servo-scheduling logic lives here.
"""

import serial                                        # Serial communication support.
import time                                          # Timing functions.
import struct                                        # Binary data packing/unpacking.
import json                                          # JSON parsing for song files.
import threading                                     # Threading primitives for cancellation.

# --- Configuration ------------------------------------------------------------

DEBUG          = True                                # Enable detailed debug output.
SERIAL_PORT    = '/dev/ttyACM0'                      # Path to Arduino serial port.
BAUD_RATE      = 115200                              # Serial communication speed.
BPM            = 120                                 # Beats per minute tempo.
ms_per_beat    = 60000.0 / BPM                       # Milliseconds duration of one beat.
SYNC_DELAY_MS  = 1000                                # Delay before first action for sync.
END_SLACK      = 1500                                 # Extra ms to ensure final action completes.
WINDOW_MS      = 10000                               # Rolling window size, 10 seconds
CHECK_INTERVAL = 1                                   # Seconds between scheduler checks

# Packet markers matching Arduino definitions.
SYNC_MARKER     = 0xAA                               # Marker for sync packet.
SYNC_TYPE       = 0x01                               # Expected type within sync packet.
COMMAND_MARKER  = 0xBB                               # Marker for pick/command packets.
GET_TIME_MARKER = 0xCC                               # Marker to request Arduino time.
END_MARKER      = 0xDD                               # Marker signalling end-of-song.
STOP_MARKER     = 0xEE                               # Marker to stop all Arduino actions.
RESET_MARKER    = 0xEF                               # Marker to reset servos to neutral positions.

# Load calibration data
with open("calibration.json", "r") as f:
    calibration = json.load(f)

# --- Cancellation support -----------------------------------------------------

stop_event = threading.Event()                       # Event flag to request song stop.

def stop_song() -> None:
    """
    Signal running play_song() to halt, and send STOP+RESET to Arduino.
    """
    stop_event.set()
    try:
        ser = connect()
        # Send STOP first
        ser.write(bytes([STOP_MARKER]))
        if DEBUG:
            print("[stop] Sent STOP_MARKER (0xEE)")
        time.sleep(0.02)  # Give Arduino time to clear state
        # Now send dynamic RESET
        send_reset(ser, calibration)
        ser.close()
    except Exception as e:
        print(f"[stop] Could not send STOP/RESET to Arduino: {e}")
    
def send_reset(ser, calibration):
    """
    Send RESET packet with all neutral servo angles (int16, big-endian).
    """
    # The order here must match your Arduino's indices: 0-5 picking, 6-17 fretting
    # Picking servos: 'e', 'A', 'D', 'G', 'B', 'E' (indices 0-5)
    pick_keys = ['e', 'A', 'D', 'G', 'B', 'E']
    angles = [int(calibration['picking'][k]['neutral']) for k in pick_keys]
    # Fretting servos: see your mapping (indices 6-17, two per string in calibration)
    fret_indices = [6,7,8,9,10,11,12,13,14,15,16,17]
    fret_strings = ['e','A','D','G','B','E','e','A','D','G','B','E']
    angles.extend([int(calibration['fretting'][s]['neutral'][str(idx)]) for s, idx in zip(fret_strings, fret_indices)])

    # Build packet: [0xEF][angle0][angle1]...[angle17], each angle as int16 big-endian
    pkt = bytearray([RESET_MARKER])
    for angle in angles:
        pkt += angle.to_bytes(2, byteorder='big', signed=True)
    ser.write(pkt)
    if DEBUG:
        print(f"[reset] Sent RESET packet: {angles}")
    # Wait for Arduino ack
    time.sleep(0.05)
    while ser.in_waiting:
        line = ser.readline().decode('utf-8','replace').strip()
        if "RESET_DONE" in line:
            if DEBUG:
                print("From Arduino:", line)
            break

# Maps indices to string names for picking servos
INDEX_TO_STRING = {0: 'e', 1: 'A', 2: 'D', 3: 'G', 4: 'B', 5: 'E'}

# --- Low-level serial / timing helpers ----------------------------------------

def connect(port: str = SERIAL_PORT, baud: int = BAUD_RATE) -> serial.Serial:
    """
    Open and initialise the serial connection to the Arduino.
    """
    ser = serial.Serial(port, baud, timeout=1)       # Open serial port with timeout.
    ser.reset_input_buffer()                         # Flush any incoming data from buffer.
    ser.reset_output_buffer()                        # Clear any pending output data.
    time.sleep(1)                                    # Give Arduino time to reboot.
    return ser                                       # Return the configured serial object.

def get_arduino_time(ser: serial.Serial) -> int:
    """
    Request and return the current millis() from the Arduino.
    """
    ser.write(struct.pack('>B', GET_TIME_MARKER))    # Send single-byte time request.
    while True:
        line = ser.readline().decode('utf-8','replace').strip()  # Read response line.
        if line.startswith("TIME:"):                  # Detect time response.
            t = int(line.split("TIME:")[1])           # Parse milliseconds value.
            if DEBUG:
                print(f"[sync] Arduino time = {t} ms")  # Log received time.
            return t                                  # Return the Arduino time.

def send_sync(ser: serial.Serial, start_time: int) -> None:
    """
    Transmit the zero-reference time to synchronize schedules.
    """
    pkt = struct.pack('>BBI', SYNC_MARKER, SYNC_TYPE, start_time)  # Create sync packet.
    ser.write(pkt)                                      # Send sync instruction.
    if DEBUG:
        print(f"[sync] Sent SYNC @ {start_time} ms")   # Confirm sync transmission.

def send_pick(ser: serial.Serial, target: int, angle: int, delay: int) -> None:
    """
    Send a pick command packet and handle Arduino debug output.
    """
    if not (0 <= angle <= 180):
        raise ValueError("Angle must be in 0-180 degrees")
    if not (0 <= delay <= 0xFFFFFFFF):
        raise ValueError("Delay must be in 0-4,294,967,295 ms")
    pkt = struct.pack('<BBBI', COMMAND_MARKER, target & 0xFF, angle & 0xFF, delay) # Pack pick data.
    ser.write(pkt)                                       # Transmit pick packet.
    if DEBUG:
        print(f"[pick] T={target} A={angle} D={delay} ms")  # Log command details.

    time.sleep(0.015)                                    # Short pause for buffer handling.
    while ser.in_waiting:                                # Process any Arduino responses.
        line = ser.readline().decode('utf-8','replace').strip()  # Read response line.
        if DEBUG:
            print("From Arduino:", line)               # Output Arduino debug.

# --- Musical primitives -------------------------------------------------------

class TimedAction:
    """
    Represents a single servo move at a scheduled time.
    """
    def __init__(self, servo: int, angle: int,
                       beat_offset: float = 0.0, ms_offset: int = 0):
        self.servo       = servo                         # Servo index to actuate.
        self.angle       = angle                         # Desired servo angle.
        self.beat_offset = beat_offset                   # Offset in beats.
        self.ms_offset   = ms_offset                     # Additional ms offset.

    def compute_delay(self, base_time: int) -> int:
        # Calculate absolute execution time in ms.
        return base_time + int(self.beat_offset * ms_per_beat) + self.ms_offset

_last_pick_side: dict[int,bool] = {}                   # Tracks pick orientation state.

class PickAction:
    """
    Alternating pick movement flipping between up/down angles.
    """
    def __init__(self, servo: int,
                       angle_up: int, angle_down: int,
                       beat_offset: float = 0.0, ms_offset: int = 0):
        self.servo       = servo                         # Pick-servo index.
        self.angle_up    = angle_up                      # Angle for upward stroke.
        self.angle_down  = angle_down                    # Angle for downward stroke.
        self.beat_offset = beat_offset                   # Offset in beats.
        self.ms_offset   = ms_offset                     # Additional ms offset.

    def compute_delay(self, base_time: int) -> int:
        # Calculate absolute execution time in ms.
        return base_time + int(self.beat_offset * ms_per_beat) + self.ms_offset
        
class FretAction:
    """
    Fret press then release after a specified duration.
    """
    def __init__(self, servo: int,
                       press_angle: int, release_angle: int,
                       beat_offset: float = 0.0, ms_offset: int = 0,
                       release_after: int = 100):
        self.servo         = servo                      # Fretting-servo index.
        self.press_angle   = press_angle               # Angle to press the fret.
        self.release_angle = release_angle             # Angle to release the fret.
        self.beat_offset   = beat_offset               # Offset in beats.
        self.ms_offset     = ms_offset                 # Additional ms offset.
        self.release_after = release_after             # Delay before automatic release.

    def compute_delay(self, base_time: int) -> int:
        # Calculate absolute execution time in ms.
        return base_time + int(self.beat_offset * ms_per_beat) + self.ms_offset

class SongCommand:
    """
    Group of actions representing a chord or note sequence.
    """
    def __init__(self, name: str, actions: list):
        self.name    = name                            # Identifier for the command.
        self.actions = actions                         # List of timed or pick/fret actions.

    def schedule(self, ser: serial.Serial, base_time: int, duration_beats: float = None) -> None:
        """
        Schedule each action by sending appropriate packets.
        If duration_beats is specified, use it to calculate release for FretActions.
        """
        if DEBUG:
            print(f"[cmd] Scheduling '{self.name}' @ {base_time} ms")  # Log command schedule.

        for act in self.actions:
            if isinstance(act, PickAction):
                d = act.compute_delay(base_time)
                was_up = _last_pick_side.get(act.servo, False)
                angle = act.angle_down if was_up else act.angle_up
                _last_pick_side[act.servo] = not was_up
                send_pick(ser, act.servo, angle, d)

            elif isinstance(act, FretAction):
                press_t = act.compute_delay(base_time)
                # Use duration_beats if given, otherwise default to 1.0 beat
                release_after = int(duration_beats * ms_per_beat) if duration_beats is not None else int(1.0 * ms_per_beat)
                release_t = press_t + release_after
                send_pick(ser, act.servo, act.press_angle, press_t)
                send_pick(ser, act.servo, act.release_angle, release_t)

            else:
                d = act.compute_delay(base_time)
                send_pick(ser, act.servo, act.angle, d)

class StrumCommand:
    """
    Represents a strum across specified strings with automatic up/down alternation.
    """
    _last_strum_up = False  # Class-level state: toggles between up and down

    def __init__(self, strings):
        self.strings = strings  # Indices of strings to strum (e.g. [0,1,2,3,4,5])

    def schedule(self, ser, base_time, duration_beats=None):
        """
        Schedule the strum: alternate direction automatically,
        strumming each specified string in order with sweep effect.
        """
        # Allow fret to happen first
        base_time = base_time + 50
        
        # Toggle direction for each strum
        StrumCommand._last_strum_up = not StrumCommand._last_strum_up
        is_up = StrumCommand._last_strum_up

        # Determine strum order (down: low to high, up: high to low)
        strum_order = list(self.strings)
        if is_up:
            strum_order = list(reversed(strum_order))

        for i, string_idx in enumerate(strum_order):
            string_name = INDEX_TO_STRING[string_idx]
            angles = get_pick_angles(string_name)
            angle = angles["up"] if is_up else angles["down"]
            delay = base_time + i * 10  # 10 ms sweep between each string
            send_pick(ser, string_idx, angle, delay)  # Send pick command

# --- Helper Functions ----------------------------------
       
def get_pick_angles(string_name: str) -> dict:
    """
    Fetch up, down, neutral angles for a picking string.
    """
    return calibration["picking"][string_name]

def get_fret_angles(string_name: str, fret_num: int) -> dict:
    """
    Fetch press, release angles and release_after for a specific string and fret.
    """
    return calibration["fretting"][string_name]["frets"][str(fret_num)]

def get_pick_neutral(string_name: str) -> int:
    return calibration["picking"][string_name]["neutral"]

def get_fret_neutral(string_name: str, servo: int) -> int:
    return calibration["fretting"][string_name]["neutral"][str(servo)]
                
def make_pick_action(string: str, servo: int, beat_offset=0.0, ms_offset=0):
    angles = get_pick_angles(string)
    return PickAction(servo, angle_up=angles["up"], angle_down=angles["down"],
                      beat_offset=beat_offset, ms_offset=ms_offset)

def make_fret_action(string: str, fret: int, servo: int, beat_offset=0.0, ms_offset=0):
    angles = get_fret_angles(string, fret)
    return FretAction(servo,
                      press_angle=angles["press"],
                      release_angle=angles["release"],
                      beat_offset=beat_offset,
                      ms_offset=ms_offset,
                      release_after=0)

def make_chord(name, *component_cmds):
    """Combine actions from multiple SongCommands into one chord SongCommand."""
    all_actions = []
    for cmd in component_cmds:
        all_actions.extend(cmd.actions)
    return SongCommand(name, all_actions)

def resolve_command(ev):
    """
    Always resolve a command to an instance (never leave as a function).
    """
    cmd_name = ev["cmd"]
    cmd = command_map.get(cmd_name)
    if cmd is None:
        raise KeyError(f"Unknown command: '{cmd_name}' in event {ev}")
    if callable(cmd):
        try:
            return cmd(ev)
        except Exception as e:
            raise RuntimeError(f"Failed to resolve callable command '{cmd_name}' with event {ev}: {e}")
    return cmd
    
# --- Pre-defined SongCommands (calibrated) -----------------------------------

RESET = SongCommand("RESET", [
    # Picking servos to neutral (one per string)
    TimedAction(0, get_pick_neutral('e'), beat_offset=0.0),
    TimedAction(1, get_pick_neutral('A'), beat_offset=0.0),
    TimedAction(2, get_pick_neutral('D'), beat_offset=0.0),
    TimedAction(3, get_pick_neutral('G'), beat_offset=0.0),
    TimedAction(4, get_pick_neutral('B'), beat_offset=0.0),
    TimedAction(5, get_pick_neutral('E'), beat_offset=0.0),
    # Fretting servos to their specific neutral angles (must specify both servo and string)
    TimedAction(6,  get_fret_neutral('e', 6),  beat_offset=0.5),
    TimedAction(7,  get_fret_neutral('A', 7),  beat_offset=0.5),
    TimedAction(8,  get_fret_neutral('D', 8),  beat_offset=0.5),
    TimedAction(9,  get_fret_neutral('G', 9),  beat_offset=0.5),
    TimedAction(10, get_fret_neutral('B', 10), beat_offset=0.5),
    TimedAction(11, get_fret_neutral('E', 11), beat_offset=0.5),
    
    TimedAction(12, get_fret_neutral('e', 12),  beat_offset=1.0),
    TimedAction(13, get_fret_neutral('A', 13),  beat_offset=1.0),
    TimedAction(14, get_fret_neutral('D', 14),  beat_offset=1.0),
    TimedAction(15, get_fret_neutral('G', 15),  beat_offset=1.0),
    TimedAction(16, get_fret_neutral('B', 16),  beat_offset=1.0),
    TimedAction(17, get_fret_neutral('E', 17),  beat_offset=1.0),
])

# Low e string
e0 = SongCommand("e0", [
    make_pick_action('e', servo=0, beat_offset=0.0, ms_offset=50)
])
e1 = SongCommand("e1", [
    make_fret_action('e', 1, servo=6, beat_offset=0.0, ms_offset=0),
    make_pick_action('e', servo=0, beat_offset=0.0, ms_offset=50)
])
e2 = SongCommand("e2", [
    make_fret_action('e', 2, servo=6, beat_offset=0.0, ms_offset=0),
    make_pick_action('e', servo=0, beat_offset=0.0, ms_offset=50)
])
e3 = SongCommand("e3", [
    make_fret_action('e', 3, servo=12, beat_offset=0.0, ms_offset=0),
    make_pick_action('e', servo=0, beat_offset=0.0, ms_offset=50)
])
e4 = SongCommand("e4", [
    make_fret_action('e', 4, servo=12, beat_offset=0.0, ms_offset=0),
    make_pick_action('e', servo=0, beat_offset=0.0, ms_offset=50)
])

# A string
A0 = SongCommand("A0", [
    make_pick_action('A', servo=1, beat_offset=0.0, ms_offset=50)
])
A1 = SongCommand("A1", [
    make_fret_action('A', 1, servo=7, beat_offset=0.0, ms_offset=0),
    make_pick_action('A', servo=1, beat_offset=0.0, ms_offset=50)
])
A2 = SongCommand("A2", [
    make_fret_action('A', 2, servo=7, beat_offset=0.0, ms_offset=0),
    make_pick_action('A', servo=1, beat_offset=0.0, ms_offset=50)
])
A3 = SongCommand("A3", [
    make_fret_action('A', 3, servo=13, beat_offset=0.0, ms_offset=0),
    make_pick_action('A', servo=1, beat_offset=0.0, ms_offset=50)
])
A4 = SongCommand("A4", [
    make_fret_action('A', 4, servo=13, beat_offset=0.0, ms_offset=0),
    make_pick_action('A', servo=1, beat_offset=0.0, ms_offset=50)
])

# D string
D0 = SongCommand("D0", [make_pick_action('D', servo=2, beat_offset=0.0, ms_offset=100)])
D1 = SongCommand("D1", [
    make_fret_action('D', 1, servo=8, beat_offset=0.0, ms_offset=0),
    make_pick_action('D', servo=2, beat_offset=0.0, ms_offset=50)
])
D2 = SongCommand("D2", [
    make_fret_action('D', 2, servo=8, beat_offset=0.0, ms_offset=0),
    make_pick_action('D', servo=2, beat_offset=0.0, ms_offset=50)
])
D3 = SongCommand("D3", [
    make_fret_action('D', 3, servo=14, beat_offset=0.0, ms_offset=0),
    make_pick_action('D', servo=2, beat_offset=0.0, ms_offset=50)
])
D4 = SongCommand("D4", [
    make_fret_action('D', 4, servo=14, beat_offset=0.0, ms_offset=0),
    make_pick_action('D', servo=2, beat_offset=0.0, ms_offset=50)
])

# G string
G0 = SongCommand("G0", [make_pick_action('G', servo=3, beat_offset=0.0, ms_offset=100)])
G1 = SongCommand("G1", [
    make_fret_action('G', 1, servo=9, beat_offset=0.0, ms_offset=0),
    make_pick_action('G', servo=3, beat_offset=0.0, ms_offset=50)
])
G2 = SongCommand("G2", [
    make_fret_action('G', 2, servo=9, beat_offset=0.0, ms_offset=0),
    make_pick_action('G', servo=3, beat_offset=0.0, ms_offset=50)
])
G3 = SongCommand("G3", [
    make_fret_action('G', 3, servo=15, beat_offset=0.0, ms_offset=0),
    make_pick_action('G', servo=3, beat_offset=0.0, ms_offset=50)
])
G4 = SongCommand("G4", [
    make_fret_action('G', 4, servo=15, beat_offset=0.0, ms_offset=0),
    make_pick_action('G', servo=3, beat_offset=0.0, ms_offset=50)
])

# B string
B0 = SongCommand("B0", [make_pick_action('B', servo=4, beat_offset=0.0, ms_offset=100)])
B1 = SongCommand("B1", [
    make_fret_action('B', 1, servo=10, beat_offset=0.0, ms_offset=0),
    make_pick_action('B', servo=4, beat_offset=0.0, ms_offset=50)
])
B2 = SongCommand("B2", [
    make_fret_action('B', 2, servo=10, beat_offset=0.0, ms_offset=0),
    make_pick_action('B', servo=4, beat_offset=0.0, ms_offset=50)
])
B3 = SongCommand("B3", [
    make_fret_action('B', 3, servo=16, beat_offset=0.0, ms_offset=0),
    make_pick_action('B', servo=4, beat_offset=0.0, ms_offset=50)
])
B4 = SongCommand("B4", [
    make_fret_action('B', 4, servo=16, beat_offset=0.0, ms_offset=0),
    make_pick_action('B', servo=4, beat_offset=0.0, ms_offset=50)
])

# High E string
E0 = SongCommand("E0", [make_pick_action('E', servo=5, beat_offset=0.0, ms_offset=50)])
E1 = SongCommand("E1", [
    make_fret_action('E', 1, servo=11, beat_offset=0.0, ms_offset=0),
    make_pick_action('E', servo=5, beat_offset=0.0, ms_offset=50)
])
E2 = SongCommand("E2", [
    make_fret_action('E', 2, servo=11, beat_offset=0.0, ms_offset=0),
    make_pick_action('E', servo=5, beat_offset=0.0, ms_offset=50)
])
E3 = SongCommand("E3", [
    make_fret_action('E', 3, servo=17, beat_offset=0.0, ms_offset=0),
    make_pick_action('E', servo=5, beat_offset=0.0, ms_offset=50)
])
E4 = SongCommand("E4", [
    make_fret_action('E', 4, servo=17, beat_offset=0.0, ms_offset=0),
    make_pick_action('E', servo=5, beat_offset=0.0, ms_offset=50)
])

# Chords
Chord_F  = make_chord("Chord_F", B1, G2, D3, A3)
Chord_G  = make_chord("Chord_G", A2, e3, E3)
Chord_C  = make_chord("Chord_C", B1, D2, A3)
Chord_Am = make_chord("Chord_Am", B1, G2, D2)
Chord_E7 = make_chord("Chord_E7", G1, A2)

# Map song commands by name for lookup during playback.
command_map: dict[str, SongCommand] = {
    # e string (high e, string 1)
    "e0": e0, "e1": e1, "e2": e2, "e3": e3, "e4": e4,
    # A string
    "A0": A0, "A1": A1, "A2": A2, "A3": A3, "A4": A4,
    # D string
    "D0": D0, "D1": D1, "D2": D2, "D3": D3, "D4": D4,
    # G string
    "G0": G0, "G1": G1, "G2": G2, "G3": G3, "G4": G4,
    # B string
    "B0": B0, "B1": B1, "B2": B2, "B3": B3, "B4": B4, 
    # E string (low E, string 6)
    "E0": E0, "E1": E1, "E2": E2, "E3": E3, "E4": E4,
    # Reset
    "RESET": RESET,
    # Strum
    "STRUM": lambda ev: StrumCommand(ev.get("strings", [0,1,2,3,4,5])),
    # Chords
    "Chord_F": Chord_F, "Chord_G": Chord_G, "Chord_C": Chord_C, "Chord_Am": Chord_Am, "Chord_E7": Chord_E7, 
}

# --- High-level play_song function -------------------------------------------
def play_song(song_name: str, songs_dir: str = "./songs", set_start_time_cb=None, on_finish_cb=None) -> None:
    """
    Load song JSON, synchronise with Arduino, flatten events,
    schedule actions, and honour cancellation requests.
    """
    stop_event.clear()                                # Reset any prior stop signal.
    ser = connect()                                   # Establish serial connection.
    try:
        # Synchronise clocks before streaming commands.
        arduino_ms      = get_arduino_time(ser)
        global_start_ms = arduino_ms + SYNC_DELAY_MS
        send_sync(ser, global_start_ms)
        
        # Set _start_time callback here, as this is when sync delay officially begins
        if set_start_time_cb is not None:
            # Pi wall time when SYNC packet is sent, minus SYNC_DELAY_MS, matches the timeline logic
            set_start_time_cb(time.time() * 1000.0 + 1000)

        time.sleep(0.1)                               # Brief pause post-sync.

        # Load song structure from JSON file.
        path = f"{songs_dir}/{song_name}.json"
        with open(path, "r") as f:
            score = json.load(f)
            
        sections_map = score.get("sections", {})     # Named section definitions.
        timeline     = score["timeline"]              # Sequence of section/note events.

        # Flatten timeline by expanding section references.
        flat_events = []
        for ev in timeline:
            beat = ev["beat"]; cmd = ev["cmd"]
            if cmd in sections_map:
                for sub in sections_map[cmd]:
                    ev_copy = dict(sub)  # Copy all fields of the sub-event (including "duration"!)
                    ev_copy["beat"] = beat + sub["beat"]  # Adjust the beat
                    flat_events.append(ev_copy)
            else:
                flat_events.append(ev)

        flat_events.sort(key=lambda e: e["beat"])      # Order events chronologically.
        if DEBUG:
            for ev in flat_events:
                print(f"[debug] beat={ev['beat']}, cmd='{ev['cmd']}', duration={ev.get('duration')}")
                
        # Determine end-of-song time including last release and slack.
        max_rel = 0
        for ev in flat_events:
            if stop_event.is_set():
                return  # Exit as soon as stop_event is set
            beat   = ev["beat"]
            
            action = resolve_command(ev)
            if action is None:
                raise KeyError(f"Unknown command: '{ev['cmd']}'")
            if callable(action):
                raise RuntimeError(f"Command {ev['cmd']} did not resolve to an instance but to a function: {action}")

            # Only SongCommand instances have 'actions'
            if hasattr(action, "actions"):
                for act in action.actions:
                    inner = getattr(act, "beat_offset", 0.0)
                    rel = int((beat + inner) * ms_per_beat) + getattr(act, "ms_offset", 0)
                    if isinstance(act, FretAction):
                        # Use per-note duration if present in event, else default to 1 beat
                        duration_beats = ev.get("duration", 1.0)
                        rel += int(duration_beats * ms_per_beat)
                    if rel > max_rel:
                        max_rel = rel
            elif isinstance(action, StrumCommand):
                # For StrumCommand, estimate delay of last string
                num_strings = len(action.strings)
                # Strum direction: first or last, both take similar max time
                strum_end = int(beat * ms_per_beat) + (num_strings - 1) * 10
                rel = strum_end
                if rel > max_rel:
                    max_rel = rel
            else:
                print(f"[error] Unexpected action type: {type(action)}, event: {ev}, command: {ev.get('cmd')}")
                raise TypeError(f"Command '{ev.get('cmd')}' did not resolve to SongCommand or StrumCommand but to {type(action)}")

        end_rel = global_start_ms + max_rel + END_SLACK  # Absolute time for END_MARKER.
        if DEBUG:
            print(f"[debug] end-of-song at {end_rel} ms")

        # Precompute absolute execution times for each event
        for ev in flat_events:
            beat = ev["beat"]
            ev["_abs_time"] = global_start_ms + int(beat * ms_per_beat)
        
        event_idx = 0
        num_events = len(flat_events)
        sent_end_marker = False

        # Stream each event to the Arduino in sequence.
        while event_idx < num_events and not stop_event.is_set():
            # Query current Arduino time (relative to sync point!)
            arduino_time = get_arduino_time(ser)
            now = arduino_time  # already ms since sync
    
            # Send any actions due within the window
            while (event_idx < num_events and flat_events[event_idx]["_abs_time"] - global_start_ms <= now + WINDOW_MS):
                ev = flat_events[event_idx]
                base_ms = ev["_abs_time"]
                duration_beats = ev.get("duration", None)
                action = resolve_command(ev)
                if action is None:
                    raise KeyError(f"Unknown command: '{ev['cmd']}'")
                if callable(action):
                    raise RuntimeError(f"Command {ev['cmd']} did not resolve to an instance but to a function: {action}")
                action.schedule(ser, base_ms, duration_beats=duration_beats)
                event_idx += 1
                
            # If all events have been sent and END_MARKER not sent, send it now
            if event_idx >= num_events and not sent_end_marker:
                end_rel = global_start_ms + max_rel + END_SLACK
                pkt = struct.pack('<BI', END_MARKER, end_rel)
                ser.write(pkt)
                sent_end_marker = True
                if DEBUG:
                    print(f"[end] Sent END_MARKER @ {end_rel} ms - awaiting DONE")
            # Wait a bit before checking Arduino time again
            time.sleep(CHECK_INTERVAL)
            
        while True:
            if stop_event.is_set():
                if DEBUG:
                    print("[end] Stop event set during DONE wait, breaking loop")
                break

            try:
                line = ser.readline().decode('utf-8', 'replace').strip()
            except Exception as e:
                if DEBUG:
                    print(f"[end] Exception during readline: {e}")
                break

            if not line:
                continue
            if DEBUG:
                print("From Arduino:", line)
            if line == "DONE":
                if DEBUG:
                    print("[end] Received DONE - playback complete")
                break
    finally:
        ser.close()                                    # Ensure serial port is closed.
        if on_finish_cb is not None:
            on_finish_cb()                             # Reset state after playback ends/stops
