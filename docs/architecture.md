# FPV Ultimate Architecture

This document expands the system diagrams from the README and explains how the browser dashboard, Flask backend, WebRTC camera path, JSON persistence, GPIO output, and failsafe behavior fit together.

## System Overview

```mermaid
flowchart LR
    Browser[Browser Dashboard<br/>Gamepad + WebRTC UI]
    Flask[Flask App<br/>Routes + Signaling]
    Camera[Picamera2 / IMX708]
    Control[ControlService<br/>Steering + Throttle + Failsafe]
    GPIO[GPIOZero + pigpio]
    Servos[Steering / Throttle / Accessories]
    Storage[JSON Settings<br/>Models + Runtime State]

    Browser -->|HTTP API| Flask
    Browser -->|WebRTC Offer| Flask
    Flask --> Camera
    Flask --> Control
    Flask --> Storage
    Control --> GPIO
    GPIO --> Servos
```

## Backend Module Layout

```mermaid
flowchart TD
    App[app.py<br/>application assembly]

    App --> Pages[pages.py]
    App --> Health[health.py]
    App --> Storage[storage.py]
    App --> SettingsRoutes[settings_models_routes.py]
    App --> AccessoryRoutes[accessory_routes.py]
    App --> Accessories[accessories.py]
    App --> ControlService[control_service.py]
    App --> ControlMath[control_math.py]
    App --> VideoConfig[video_config.py]
    App --> SystemActions[system_actions.py]

    SettingsRoutes --> Storage
    AccessoryRoutes --> Accessories
    ControlService --> ControlMath
```

## Browser Control Flow

```mermaid
sequenceDiagram
    participant User as User / DualSense
    participant Browser as Browser Dashboard
    participant Flask as Flask /api/control
    participant Control as ControlService
    participant GPIO as GPIOZero + pigpio
    participant Servo as Steering/Throttle Servo

    User->>Browser: Move stick / triggers
    Browser->>Browser: Compute steer/throttle degrees
    Browser->>Flask: POST /api/control
    Flask->>Control: apply_control(steer, throttle, speeds)
    Control->>Control: Clamp + smooth command
    Control->>GPIO: Set AngularServo.angle
    GPIO->>Servo: PWM output
```

## Failsafe Flow

```mermaid
flowchart TD
    Start[Failsafe worker loop]
    Read[Read failsafe_enabled setting]
    Stale{Input stale longer<br/>than timeout?}
    Neutral[Neutralize steering/throttle<br/>to 90 degrees]
    Wait[Wait 20ms]

    Start --> Read
    Read --> Stale
    Stale -->|No| Wait
    Stale -->|Yes| Neutral
    Neutral --> Wait
    Wait --> Start
```

The failsafe worker does not depend on the browser. It uses backend state inside `ControlService` and returns outputs to neutral if control input stops updating.

## WebRTC Video Flow

```mermaid
sequenceDiagram
    participant Browser as Browser Dashboard
    participant Flask as Flask /offer
    participant RTC as RTCPeerConnection
    participant Cam as Picamera2 CameraVideoTrack
    participant Camera as IMX708 / Pi Camera

    Browser->>Flask: POST /offer SDP
    Flask->>RTC: Create RTCPeerConnection
    Flask->>Cam: Attach CameraVideoTrack
    Cam->>Camera: capture_array("main")
    Flask->>Browser: Return SDP answer
    Camera-->>Browser: Video frames over WebRTC
```

## Settings and Model Flow

```mermaid
flowchart LR
    UI[Dashboard Settings UI]
    Routes[settings_models_routes.py]
    Storage[storage.py]
    Files[data/settings.json<br/>data/models.json]
    Runtime[Runtime SETTINGS dict]

    UI -->|GET/POST /api/settings| Routes
    UI -->|GET/POST model APIs| Routes
    Routes --> Storage
    Storage --> Files
    Routes --> Runtime
```

## Accessory Flow

```mermaid
flowchart LR
    UI[Dashboard Accessory Controls]
    Routes[accessory_routes.py]
    Settings[Runtime SETTINGS]
    Helper[accessories.py]
    GPIO[GPIOZero AngularServo]
    Hardware[Transmission / Lights]

    UI -->|/api/lights<br/>/api/transmission| Routes
    Routes --> Settings
    Routes --> Helper
    Helper --> GPIO
    GPIO --> Hardware
```

## Runtime Boundary

GitHub Actions checks syntax only. Hardware-backed runtime behavior is tested on the Raspberry Pi because the following dependencies are Pi-specific:

- `libcamera`
- `Picamera2`
- GPIO hardware access
- `pigpio`
- physical servo/ESC behavior

Recommended Pi-side validation after meaningful changes:

```bash
python -m py_compile app.py fpv_ultimate/*.py
curl -s http://127.0.0.1:5000/ping
curl -s http://127.0.0.1:5000/api/settings | python3 -m json.tool
curl -s http://127.0.0.1:5000/api/models | python3 -m json.tool
curl -s http://127.0.0.1:5000/api/accessories | python3 -m json.tool
curl -s -X POST http://127.0.0.1:5000/api/control \
  -H "Content-Type: application/json" \
  -d '{"steer":90,"throttle":90}' | python3 -m json.tool
```
