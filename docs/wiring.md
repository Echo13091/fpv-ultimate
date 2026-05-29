# FPV Ultimate Wiring Guide

This guide covers Raspberry Pi FPV Ultimate wiring for PWM servo signals, buck converter power, and common ground.

## Safety First

This project controls real moving hardware.

Before testing:

- Keep wheels off the ground.
- Verify buck converter output with a multimeter before connecting electronics.
- Do not power servos from the Raspberry Pi 5V pin.
- Use an external BEC or buck converter for servo and accessory power.
- Raspberry Pi ground and external servo power ground must be connected together.
- Confirm throttle neutral before applying drive power.
- Confirm failsafe returns throttle and steering to neutral.

## GPIO Pin Map

| Function | GPIO | Physical Pin | Type |
|---|---:|---:|---|
| Steering servo | GPIO12 | Pin 32 | PWM signal |
| Throttle / ESC | GPIO13 | Pin 33 | PWM signal |
| Transmission accessory | GPIO6 | Pin 31 | PWM signal |
| Lights accessory | GPIO21 | Pin 40 | PWM signal |
| Ground | GND | Pin 6/9/14/20/25/30/34/39 | Common ground |

## Main Power Concept

The Raspberry Pi GPIO pins should provide signal only.

Use a buck converter or BEC to power servos/accessories.

TEXT DIAGRAM:

Battery +  ---> Buck IN+
Battery -  ---> Buck IN-

Buck OUT+ ---> Servo/accessory positive rail
Buck OUT- ---> Servo/accessory ground rail
Pi GND    ---> Servo/accessory ground rail

Pi GPIO12 ---> Steering signal
Pi GPIO13 ---> Throttle/ESC signal
Pi GPIO6  ---> Transmission signal
Pi GPIO21 ---> Lights signal

## Buck Converter Wiring

A buck converter steps battery voltage down to a safe voltage for servos.

Battery +  -> Buck IN+
Battery -  -> Buck IN-
Buck OUT+  -> Servo/accessory V+
Buck OUT-  -> Servo/accessory GND
Buck OUT-  -> Raspberry Pi GND

Before connecting servos:

1. Connect battery to buck converter input.
2. Measure OUT+ and OUT- with a multimeter.
3. Adjust output voltage to the required servo voltage.
4. Connect servo/accessory power only after voltage is correct.

Typical servo voltage is usually 5V to 6V, but always check the rating for your hardware.

## Common Ground

Common ground is required.

Correct wiring:

Pi GPIO signal -> Servo signal wire
Buck OUT+     -> Servo positive wire
Buck OUT-     -> Servo ground wire
Pi GND        -> Buck OUT-

Incorrect wiring:

Pi GPIO signal -> Servo signal wire
Buck OUT+     -> Servo positive wire
Buck OUT-     -> Servo ground wire
Pi GND not connected to Buck OUT-

Without common ground, the servo may jitter, ignore commands, or move unpredictably.

## Servo Wire Colors

Common servo wire colors:

| Wire Color | Usually Means |
|---|---|
| Brown / Black | Ground |
| Red | Positive power |
| Yellow / Orange / White | Signal |

Always verify your specific servo or ESC wiring.

## Steering Servo

Current app configuration:

- GPIO: GPIO12
- Physical pin: 32
- Pulse width: 500us to 2500us
- Angle range: 0 to 180 degrees
- Neutral: 90 degrees

Wiring:

GPIO12 -> Steering signal
Buck + -> Steering servo V+
Buck - -> Steering servo GND
Pi GND -> Buck -

## Throttle / ESC

Current app configuration:

- GPIO: GPIO13
- Physical pin: 33
- Pulse width: 500us to 2500us
- Angle range: 0 to 180 degrees
- Neutral: 90 degrees

Wiring:

GPIO13 -> ESC/throttle signal
ESC GND -> Common ground
Pi GND -> Common ground

Test throttle with wheels off the ground.

## Transmission Accessory

Current app configuration:

- GPIO: GPIO6
- Physical pin: 31
- Pulse width: 1000us to 2000us
- Low angle: 0 degrees
- High angle: 180 degrees

Wiring:

GPIO6 -> Transmission servo/switch signal
Buck + -> Transmission servo/switch V+
Buck - -> Transmission servo/switch GND
Pi GND -> Buck -

## Lights Accessory

Current app configuration:

- GPIO: GPIO21
- Physical pin: 40
- Pulse width: 1000us to 2000us
- Off angle: 0 degrees
- On angle: 180 degrees

Wiring:

GPIO21 -> Lights servo/switch signal
Buck + -> Lights servo/switch V+
Buck - -> Lights servo/switch GND
Pi GND -> Buck -

## Full Wiring Diagram

Raspberry Pi 4:

GPIO12 Pin 32 -> Steering servo signal
GPIO13 Pin 33 -> ESC/throttle signal
GPIO6  Pin 31 -> Transmission signal
GPIO21 Pin 40 -> Lights signal
GND            -> Buck OUT- / servo ground rail

Power:

Battery + -> Buck IN+
Battery - -> Buck IN-
Buck OUT+ -> Servo/accessory V+ rail
Buck OUT- -> Servo/accessory GND rail
Pi GND    -> Servo/accessory GND rail

## Bench Test Order

1. Power the Raspberry Pi.
2. Confirm the app starts.
3. Confirm /ping works.
4. Power the buck converter with no servos connected.
5. Measure buck output voltage.
6. Connect steering servo.
7. Confirm steering neutral.
8. Connect throttle/ESC signal with wheels off ground.
9. Confirm throttle neutral.
10. Confirm failsafe returns throttle and steering to neutral.
11. Connect accessories one at a time.

## Troubleshooting

### Servo jitters

Likely causes:

- No common ground
- Weak buck converter/BEC
- Incorrect GPIO pin
- Bad connector
- Servo drawing too much current

### Pi reboots when servo moves

Likely cause:

Servo is pulling power from the Pi or shared supply is sagging.

Fix:

- Use separate servo power from a buck converter/BEC.
- Keep grounds common.
- Do not power servos from the Pi 5V pin.

### Servo does not move

Check pigpio:

systemctl status pigpiod --no-pager -l

Start pigpio:

sudo systemctl enable --now pigpiod
