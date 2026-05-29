# FPV Ultimate

A Raspberry Pi based FPV remote-control vehicle platform using a Flask web interface, WebRTC video streaming, Picamera2, GPIOZero servo control, and browser gamepad input.

This project is designed for real hardware: Raspberry Pi camera video, servo steering/throttle, browser-based control, and safety behavior for RC/FPV experiments.

## Features

- Low-latency browser video using WebRTC
- Raspberry Pi camera support through Picamera2
- Steering and throttle servo control
- Browser-based PS5 DualSense/gamepad control
- Failsafe neutral return when control input stops
- Adjustable trims, rates, smoothing, reversing, and video settings
- Servo-based accessory control for transmission and lights
- Model profile storage using JSON files
- Local Flask API for browser control and configuration

## Current Hardware Mapping

| Function | GPIO |
|---|---:|
| Steering servo | GPIO12 |
| Throttle servo | GPIO13 |
| Transmission accessory servo | GPIO6 |
| Lights accessory servo | GPIO21 |

## Project Structure

```text
fpv-ultimate/
+-- app.py
+-- requirements.txt
+-- README.md
+-- .env.example
+-- .gitignore
+-- data/
¦   +-- models.json
¦   +-- settings.json
+-- static/
¦   +-- main.js
+-- templates/
¦   +-- index.html
+-- docs/
```

## Runtime Data

Runtime settings and model profiles are stored in:

```text
data/settings.json
data/models.json
```

These files are currently committed because they act as starter/default configuration for the project. Later, they can be replaced with example files if the project needs per-device private configuration.

## Environment Variables

Example values are shown in `.env.example`:

```text
FPV_HOST=127.0.0.1
FPV_PORT=5000
FPV_DATA_DIR=data
```

| Variable | Purpose | Default |
|---|---|---|
| `FPV_HOST` | Flask bind host | `127.0.0.1` |
| `FPV_PORT` | Flask bind port | `5000` |
| `FPV_DATA_DIR` | Folder for settings/model JSON | `data` |

## Install

This project is intended to run on Raspberry Pi OS with camera and GPIO hardware available.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Depending on the Pi setup, some camera/GPIO packages may need to be installed through Raspberry Pi OS packages instead of only `pip`.

## Run

```bash
python app.py
```

By default the app runs on:

```text
http://127.0.0.1:5000
```

## API Overview

| Route | Method | Purpose |
|---|---|---|
| `/` | GET | Main control UI |
| `/ping` | GET | Basic health check |
| `/offer` | POST | WebRTC offer/answer negotiation |
| `/api/control` | POST | Steering/throttle servo command |
| `/api/transmission` | POST | Toggle or set transmission accessory |
| `/api/lights` | POST | Toggle or set lights accessory |
| `/api/accessories` | GET | Read accessory state |
| `/api/settings` | GET/POST | Read or update runtime settings |
| `/api/models` | GET | List model profiles |
| `/api/models/save` | POST | Save model profile |
| `/api/models/delete` | POST | Delete/reset model profile |
| `/api/models/rename` | POST | Rename model profile |
| `/api/reboot` | POST | Reboot Raspberry Pi |

## Safety Notes

The app includes a failsafe behavior that returns steering and throttle to neutral if control input stops. This is important for RC/FPV testing because browser, network, or controller disconnects should not leave the vehicle driving.

Test with wheels off the ground before running on a vehicle.

## Refactor Status

This repository started as a working Raspberry Pi project import.

Current state:

- Working single-file Flask app
- WebRTC camera stream
- GPIOZero servo control
- Browser gamepad UI
- JSON settings/model persistence

Planned refactor:

- Separate GPIO/servo control from Flask routes
- Separate camera/WebRTC logic from app startup
- Move settings/model storage into a dedicated module
- Add safer hardware initialization
- Add clearer install/run documentation
- Add systemd service example for Raspberry Pi deployment

## License

No license has been selected yet.
