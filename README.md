# Autonomous Guitar
A Raspberry-Pi-driven robot that frets, strums, and plucks a six-string guitar – no human fingers required.

This was made as a capstone project for UCL Mechanical Engineering (2025).

## Media
![Overall Photo](docs/images/overall_photo.JPG)

**Watch it play:**

[![Watch the playlist on YouTube](https://img.youtube.com/vi/PY2tfHVHB4E/hqdefault.jpg)](https://www.youtube.com/playlist?list=PLb9mSR-lN_d_GtLbXkXRv01xG--_rrkUY)

## Features
- **18‑servo mechanism** – 6 high‑torque picking servos over the sound‑hole, 12 micro‑servos fretting up the neck.
- **Dual‑MCU architecture** – Arduino Mega handles sub‑millisecond PWM; Raspberry Pi 5 schedules songs and hosts a Flask web UI.
- **JSON song format** – write riffs or full arrangements with chords, strums and sections.
- **REST API & touchscreen UI** – start/stop playback or query progress from any device.
- **Open‑source hardware** – full wiring diagram and bill‑of‑materials.

## Installation
Full step‑by‑step instructions live in the [**User Guide**](docs/user_guide.md).

## Repository map
```
Arduino/          RemoteScheduler.ino + project‑local libraries
RasPi/            Flask web app, scheduler & calibration.json
Raspi/songs/      Example JSON scores
docs/             Full user guide & wiring digrams
```

## Contact
This project is no longer being worked on and is here for documentation purposes only. Questions are welcome.

Email: juliantanjunan@gmail.com
