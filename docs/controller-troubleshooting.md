# Controller Troubleshooting

FPV Ultimate uses the browser Gamepad API for controller input. The browser must see the correct controller directly.

Tools like DS4Windows, HidHide, Steam Input, or other virtual controller drivers can make the dashboard show a controller as connected while still sending neutral or incorrect values.

## Known Issue: DS4Windows / HidHide

If the dashboard shows the gamepad connected but steering and throttle do not respond, check whether DS4Windows or HidHide is running.

Common symptoms:

- The gamepad status pill says connected.
- `/api/control` requests are being sent.
- Steering and throttle stay near neutral.
- A direct backend test with `curl /api/control` still moves the servo.
- Turning off DS4Windows fixes controller input.

Cause:

DS4Windows can create a virtual Xbox controller while HidHide hides the physical DualSense. Chrome or Edge may then see the wrong device, a stale device, or a neutral virtual device.

## Recommended Browser Setup

Use one clean controller path.

### Option A: Native DualSense

Recommended for this project.

- Turn off DS4Windows.
- Disable HidHide hiding/cloaking.
- Reconnect the controller.
- Restart or hard-refresh the browser.
- Open the dashboard.
- Press a controller button after the page loads.

### Option B: DS4Windows Virtual Controller

Only use this if needed.

- DS4Windows is running.
- HidHide hides the physical DualSense.
- The browser sees only one virtual Xbox controller.

Do not let the browser see both the physical DualSense and a virtual controller at the same time.

## Quick Fix Checklist

1. Close DS4Windows.
2. Disable HidHide device hiding.
3. Unplug/replug the controller or reconnect Bluetooth.
4. Restart Chrome or Edge.
5. Open the dashboard.
6. Press a controller button.
7. Refresh with `Ctrl+F5` if needed.

## Verify Backend vs Browser

If unsure whether the problem is browser input or GPIO output, test the backend directly from the Pi:

```bash
curl -s -X POST http://127.0.0.1:5000/api/control \
  -H "Content-Type: application/json" \
  -d '{"steer":60,"throttle":90}'
```

Then center steering and throttle:

```bash
curl -s -X POST http://127.0.0.1:5000/api/control \
  -H "Content-Type: application/json" \
  -d '{"steer":90,"throttle":90}'
```

If the servo moves from the `curl` command, the Raspberry Pi, Flask backend, GPIO, pigpio, and servo wiring are working. The issue is likely browser/controller mapping or DS4Windows/HidHide.

## Useful Browser Diagnostic

Open one of these pages in the browser:

```text
chrome://gamepad-internals
edge://gamepad-internals
```

Move the sticks and triggers and confirm the values change.

## Notes

The dashboard can only act on the values the browser reports. If a virtual controller driver reports neutral values, FPV Ultimate will keep sending neutral steering/throttle even though the gamepad appears connected.
