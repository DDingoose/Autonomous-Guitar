#!/usr/bin/env python3
from flask import Flask, jsonify, request           # Import Flask web framework components.
import threading                                     # Import threading for background playback.
import os                                            # Import os for filesystem operations.
import time                                         # Import time for timestamps.
import json                                         # Import json for parsing song files.
import logging                                      # Import logging to configure server logs.

import scheduler                                    # Import scheduler module for song playback.
from scheduler import play_song, stop_song          # Import core playback controls.
from scheduler import ms_per_beat, SYNC_DELAY_MS    # Import timing constants.
from scheduler import resolve_command

# Silence Flask's default access logs below WARNING level to reduce console noise.
logging.getLogger('werkzeug').setLevel(logging.WARNING)

app = Flask(__name__)                                # Initialise Flask application instance.

# Reset state funciton
def reset_playback_state():
    global _play_thread, _current_song, _start_time, _song_length_ms
    _play_thread = None
    _current_song = None
    _start_time = 0.0
    _song_length_ms = 0
    
# Thread watcher to join and reset state
def watch_playback_thread():
    global _play_thread
    if _play_thread:
        _play_thread.join()  # Wait for play_song thread to exit
    reset_playback_state()

def _playback_finished():
    reset_playback_state()

# Track playback state: background thread, current song, start time, and length.
_play_thread: threading.Thread | None = None          # Thread object running play_song().
_current_song: str | None = None                      # Name of song currently playing.
_start_time: float = 0.0                              # Pi timestamp when song starts (ms).
_song_length_ms: int = 0                              # Total song duration in ms.

# --- Route: Serve front-end --------------------------------------------------

@app.route('/')
def index():
    # Serve the main UI page from static files.
    return app.send_static_file('index.html')

# --- Route: List available songs --------------------------------------------

@app.route('/songs', methods=['GET'])
def list_songs():
    """
    Return list of JSON song filenames (without extension).
    """
    files = os.listdir('./songs')                    # List all files in songs directory.
    names = [f[:-5] for f in files if f.endswith('.json')]  # Filter .json and strip suffix.
    return jsonify(names)                            # Return names as JSON array.

# --- Route: Start song playback ---------------------------------------------

@app.route('/play', methods=['POST'])
def start_playback():
    """
    Launch play_song(song) in background thread based on POST JSON {"song": name}.
    """
    global _play_thread, _current_song, _start_time, _song_length_ms

    data = request.get_json(silent=True)            # Parse JSON payload safely.
    if not data or 'song' not in data:
        # Reject requests lacking required 'song' field.
        return jsonify({'error': 'Missing "song" parameter'}), 400

    song = data['song']                             # Extract requested song name.
    filepath = f'./songs/{song}.json'
    if not os.path.isfile(filepath):
        # Return not-found if the song file does not exist.
        return jsonify({'error': f'No such song: {song}'}), 404

    if _play_thread and _play_thread.is_alive():
        # Prevent overlapping playback sessions.
        return jsonify({'status': 'already playing', 'song': _current_song}), 409

    # Pre-load and flatten song JSON to compute total duration.
    with open(filepath) as f:
        score = json.load(f)                        # Load song structure.
    sections = score.get('sections', {})
    timeline = score['timeline']

    flat = []                                       # Flattened list of events.
    for ev in timeline:
        beat, cmd = ev['beat'], ev['cmd']
        if cmd in sections:
            # Expand named sections into individual events.
            for sub in sections[cmd]:
                flat.append({'beat': beat + sub['beat'], 'cmd': sub['cmd']})
        else:
            flat.append(ev)                         # Keep atomic events.

    # Compute playback length in ms including fret-release slack.
    max_rel = 0
    for ev in flat:
        beat, cmd = ev['beat'], ev['cmd']
        action = resolve_command(ev)
        if action is None:
            raise KeyError(f"Unknown command: '{ev['cmd']}'")
        if callable(action):
            raise RuntimeError(f"Command {ev['cmd']} did not resolve to an instance but to a function: {action}")

        if hasattr(action, "actions"):
            for act in action.actions:
                rel = int(beat * ms_per_beat) + getattr(act, 'ms_offset', 0)
                if isinstance(act, scheduler.FretAction):
                    rel += act.release_after            # Include release delay.
                if rel > max_rel:
                    max_rel = rel                       # Track maximum relative time.
        elif isinstance(action, scheduler.StrumCommand):
            num_strings = len(action.strings)
            strum_end = int(beat * ms_per_beat) + (num_strings - 1) * 15
            rel = strum_end
            if rel > max_rel:
                max_rel = rel
        else:
            print(f"[error] Unexpected action type: {type(action)}, event: {ev}, command: {ev.get('cmd')}")
            raise TypeError(f"Command '{ev.get('cmd')}' did not resolve to SongCommand or StrumCommand but to {type(action)}")


    _song_length_ms = scheduler.SYNC_DELAY_MS + max_rel + scheduler.END_SLACK + 1500  # Include sync delay.

    # Record Pi-side start time for progress tracking (ms).
    _start_time = time.time() * 1000.0
    
    def set_start_time_cb(val):
        global _start_time
        _start_time = val
        
    # Start the thread, passing the callback:
    _play_thread = threading.Thread(
        target=play_song,
        args=(song,),
        kwargs={
            'set_start_time_cb': set_start_time_cb,
            'on_finish_cb': _playback_finished
        },
        daemon=True
    )

    # Launch playback in daemon thread to avoid blocking server.
    _current_song = song
    _play_thread.start()                             # Begin asynchronous playback.

    return jsonify({'status': 'started', 'song': song})

# --- Route: Stop current playback -------------------------------------------

@app.route('/stop', methods=['POST'])
def stop_playback():
    global _play_thread
    thread = _play_thread
    if thread and thread.is_alive():
        stop_song()
        try:
            thread.join(timeout=2.0)
        except Exception as e:
            print(f"[stop] Exception during join: {e}")
        reset_playback_state()
        return jsonify({'status': 'stopping', 'song': _current_song})
    reset_playback_state()
    return jsonify({'status': 'idle'})

# --- Route: Playback status -------------------------------------------------

@app.route('/status', methods=['GET'])
def get_status():
    """
    Report whether playback is active and current song name.
    """
    playing = _play_thread is not None and _play_thread.is_alive()
    return jsonify({
        'state': 'playing' if playing else 'idle',
        'song':  _current_song if playing else None
    })

# --- Route: Playback progress -----------------------------------------------

@app.route('/progress', methods=['GET'])
def get_progress():
    # Calculate playback percentage based on elapsed time.
    playing = _play_thread is not None and _play_thread.is_alive()
    if not playing:
        return jsonify({'state': 'idle', 'pct': 0.0})

    now_ms = time.time() * 1000.0                   # Current Pi timestamp in ms.
    elapsed_ms = now_ms - _start_time               # Time since start.
    
    # Wait until sync phase is complete
    if elapsed_ms < SYNC_DELAY_MS:
        pct = 0.0 # Progress bar stays at 0 during sync delay
    else:
        # Only count progress after sync delay
        song_progress_ms = elapsed_ms - SYNC_DELAY_MS
        bar_length_ms = _song_length_ms - SYNC_DELAY_MS
        pct = min(1.0, song_progress_ms / bar_length_ms)
    return jsonify({'state': 'playing', 'pct': pct})

if __name__ == '__main__':
    # Use built-in Flask server for simplicity.
    app.run(host='0.0.0.0', port=5000)            # Listen on all interfaces port 5000.

