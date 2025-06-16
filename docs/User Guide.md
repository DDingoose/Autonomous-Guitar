# Important Note
In its current state, the Raspberry Pi does not have the software installed. I set up a fresh copy of the OS, anticipating that future users (students working on a capstone project) would iterate on it from a clean slate. As a result, the Raspberry Pi is not ready for immediate use and will need some time for software installation and setup. 

However, everything else should be in place. The Arduino should already contain the required sketch, and most of the wires should be connected.

Thus, to get the autonomous guitar working, you need to connect the Power Supply wires and install the Raspberry Pi software.

# 1. Introduction
- High-level architecture: Pi ⇄ Serial ⇄ Arduino Mega ⇄ I²C ⇄ PCA9685 ⇄ Servos.
- 
# 2.  Bill of Materials

| Qty | Item                               | Notes                                                 |
| --- | ---------------------------------- | ----------------------------------------------------- |
| 1   | Classical/acoustic guitar          | Holes drilled to attach picking unit                  |
| 6   | Servos (picking)                   |                                                       |
| 12  | Servos (fretting)                  |                                                       |
| 2   | PCA9685 16‑channel PWM boards      | I²C addresses 0x40 & 0x41                             |
| 1   | Arduino Mega 2560                  | USB cable for Pi connection                           |
| 1   | Raspberry Pi 5 (+ micro‑SD, power) | Runs Flask web app                                    |
| 1   | 5 V power supply                   | IMPORTANT: Must be set to around 5 V to work properly |

# 3. Electronics & Wiring
## 3.1 Power Topology
- 5 V supply → PCA9685 external +ve and -ve screw terminals → servos.
- Pi USB-C may be fed by the SMPS or its own PSU
- Grounds: tie Pi GND, Arduino GND, servo GND together.

## 3.2 Connections
A diagram is given below.

### Switched-Mode Power Supply (SMPS)
A shared power rail (on Power Supply) powers two driver boards and the Raspberry Pi

| From         | To         | Notes    |
| ------------ | ---------- | -------- |
| Mains Outlet | IEC Module |          |
| IEC inlet L  | SMPS L     | Switched |
| IEC inlet N  | SMPS N     |          |
| IEC inlet E  | SMPS E     | Earth    |

### Fretting Servo Driver
The Fretting Servo Driver uses external 5 V DC power from the Power Supply and receives I2C data and logic 5V from the Picking Servo Driver (daisy-chained).

| From             | To      | Notes         |
| ---------------- | ------- | ------------- |
| Arduino SDA (20) | SDA     | I²C data      |
| Arduino SCL (21) | SCL     | I²C clock     |
| Arduino 5 V      | VCC     | Logic only    |
| SMPS Output +ve  | EXT +ve | Servo power   |
| SMPS Output -ve  | EXT -ve | Common return |

### Picking Servo Driver
The Picking Servo Driver uses external 5 V DC power from the Power Supply and receives I2C data and logic 5V from the Arduino. The Picking Servo Driver also sends I2C data and logic 5V to the Fretting Servo Driver.

| From              | To      | Notes       |
| ----------------- | ------- | ----------- |
| Picking Servo SDA | SDA     | Daisy-chain |
| Picking Servo SCL | SCL     |             |
| Picking Servo VCC | VCC     |             |
| Picking Servo GND | GND     |             |
| SMPS Output +ve   | EXT +ve | Servo power |
| SMPS Output -ve   | EXT -ve |             |

### Arduino Mega
The Arduino Mega has a serial connection with the Raspberry Pi and sends I2C signals to the servo driver boards.

| From               | To            | Notes       |
| ------------------ | ------------- | ----------- |
| Raspberry Pi USB A | Arduino USB B | Serial data |

### Raspberry Pi
The Raspberry Pi receives 5V power from the Power Supply via a USB C cable and serial commands to the Arduino.

| From            | To      | Notes |     |
| --------------- | ------- | ----- | --- |
| SMPS Output +ve | EXT +ve | Power |     |
| SMPS Output -ve | EXT -ve |       |     |

If Pi instability is observed, it can also be powered by a dedicated USB-C wall adaptor.

### Wiring Diagram
![Wiring diagram](img/autonomous_guitar_wiring.png)

## 3.3 I²C Addressing
*This step should already be done, but I am leaving it here just in case.*

| Board | Function        | A0  | A1  | A2  | I²C address |
| ----- | --------------- | --- | --- | --- | ----------- |
| **0** | Fretting servos | 0   | 0   | 0   | `0x40`      |
| **1** | Picking servos  | 1   | 0   | 0   | `0x41`      |

## 3.4 Servo Channel Map

|Logical index|Function|Board|Channel|
|--:|---|--:|--:|
|0 – 5|Picking strings e A D G B E|1|0–5|
|6 – 11|Fretting (lower half)|0|0–5|
|12 – 17|Fretting (upper half)|0|6–11|

# 4. Firmware Upload (Arduino Mega)
*These steps should already be done (i.e., the Arduino should already be set up), but I am leaving them here just in case.*

1. **Install Arduino IDE** 
 Download at: https://www.arduino.cc/en/software/

2. **Copy the supplied libraries**
The repository already contains patched versions of the required libraries:
```
Autonomous-Guitar/
└─ Arduino/
   ├─ libraries/
   │   ├─ Adafruit_PWM_Servo_Driver_Library
   │   ├─ RemoteControl
   │   └─ ServoControl
   └─ RemoteScheduler/RemoteScheduler.ino
```

To download code from GitHub, click **Code → Download ZIP**

3. **Locate your local Arduino libraries folder**
_Windows_: `Documents\Arduino\libraries`  
_macOS/Linux_: `~/Arduino/libraries`

4. **Install required libraries**
Drag-and-drop everything inside `Autonomous-Guitar/Arduino/libraries/` into that folder

5. **Open the sketch**
In the IDE choose **File → Open…** and select: 
`Autonomous-Guitar/Arduino/RemoteScheduler/RemoteScheduler.ino`

6. **Select board and port**
- **Tools → Board** → _Arduino Mega or Mega 2560_
- **Tools → Processor** → _ATmega2560 (Mega 2560)_
- **Tools → Port** – pick the **serial/USB port** that appears when you plug the Mega in (e.g. `COM4` on Windows, `/dev/ttyACM0` on Linux).

7. **Compile & upload**
- Click **✓ Verify** – the sketch should compile without warnings.
- Click **→ Upload** – flashing takes a few seconds.
On success the IDE shows **“Done uploading.”**

7. **Confirm serial output**
- Open **Tools → Serial Monitor**.
- Set **baud = 115200** and **line ending = “Newline”**.
- You should see: `RemoteControl: Servo drivers initialised.`

# 5. Software Installation (Raspberry Pi)
 1. **Flash Raspberry Pi OS & enable SSH / serial**
*This step should already be done, but I am leaving it here just in case.*

Refer to this webpage for more info: https://www.raspberrypi.com/documentation/computers/getting-started.html#installing-the-operating-system

2. **Enable the touchscreen in the config**
*This step should already be done, but I am leaving it here just in case.*

Refer to this webpage for more info: https://www.waveshare.com/wiki/5inch_DSI_LCD#Method_1:_Use_Raspberry_Pi_Imager_to_Flash_Latest_Official_Image

Open microSD card on a laptop and edit the `config.txt` in the root directory. At the end of the config, add the following.
```
dtoverlay=vc4-kms-v3d
#DSI1 Use
dtoverlay=vc4-kms-dsi-7inch
#DSI0 Use（Only Pi5/CM4）
#dtoverlay=vc4-kms-dsi-7inch,dsi0
```

 3. **Install Pi dependencies**
```
# Update the operating system
sudo apt update && sudo apt full-upgrade -y

#Reboot the system
sudo reboot
```

 4. **Get the code**
```
# Clone the full repository
git clone https://github.com/DDingoose/Autonomous-Guitar.git
cd Autonomous-Guitar/RasPi
```

If you cannot use Git, click **Code → Download ZIP** on GitHub then copy the `RasPi` folder to the Pi and continue in that directory.

5. **Install Python dependencies**
```
pip install -r requirements.txt
```

This installs flask and pyserial.

6. **Start Flask server**
```
# Run web app
python app.py
```

You should see: `Running on http://<Pi-IP-address>5000/ (Press CTRL+C to quit)`

7. **Launch web app in Chromium**
```
# Launch Chromium in kiosk mode (full screen)
chromium-browser --kiosk <Pi-IP-address>:5000

# For example, for IP address 127.0.0.1:
chromium-browser --kiosk 127.0.0.1:5000
```

8. **(Optional) Enable autostart on boot**
Create `/etc/systemd/system/autonomous-guitar.service`:
```
[Unit]
Description=Autonomous Guitar Web App
After=network.target

[Service]
User=pi
WorkingDirectory=/home/pi/Autonomous-Guitar/RasPi
ExecStart=/home/pi/Autonomous-Guitar/RasPi/venv/bin/python app.py
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

```
sudo systemctl daemon-reload
sudo systemctl enable --now autonomous-guitar
```

9. **Copy / edit user assets**
- `songs/` – place your song JSON files here.
- `static/` – front-end HTML/JS/CSS. Adjust if you customise the web UI.
- `calibration.json` – update neutral/press/release angles to match your own servos.



# 6. Playing a Song
- Copy JSON scores into `songs/`.
- Web UI: **Play**, **Stop**, progress bar.

# Troubleshooting

# Other Notes
## Calibration
Edit `calibration.json` – fill in neutral, up, down, press, release angles.
