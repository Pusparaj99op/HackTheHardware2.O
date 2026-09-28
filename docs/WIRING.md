# VisionPilot — Complete Wiring Guide

**Firmware:** `visionpilot_esp32.ino` (simplified: WiFi AP + L298N motor + Servo)  
**Last updated:** 2026-09-29

---

## 1. Components List

| # | Component | Part / Model | Voltage | Role |
|---|-----------|-------------|---------|------|
| 1 | Microcontroller | ESP32 Dev Board (38-pin) | 3.3V logic, 5V VIN | WiFi AP, UDP server, PWM output |
| 2 | Motor Driver | L298N H-Bridge Module | VSS: 7–35V, Logic: 5V | Controls DC motor speed + direction |
| 3 | DC Motor | Hobby DC motor (RC car rear) | 6–12V | Drives the rear wheels |
| 4 | Servo | 5V hobby servo (SG90 / MG90S) | 4.8–6V | Steers front wheels |
| 5 | Battery | 7.4V 2S LiPo (or 3×AA=4.5V for testing) | 7.4V (LiPo) | Main power source |
| 6 | Buck Converter | LM2596 / XL4016 adjustable step-down | Input 7–35V → Output 5V | Supplies 5V to ESP32 + Servo |
| 7 | USB Cable | USB-A to USB-C (or Micro-USB) | 5V | Flashing only (from PC) |

---

## 2. Power Wiring (MOST IMPORTANT — DO THIS FIRST)

### 2.1 Battery to L298N (Motor Power)

```
Battery (+) red wire  ──────────────────────────► L298N  VSS terminal  (screw terminal, labelled +12V)
Battery (-) black wire ──────────────────────────► L298N  GND terminal  (screw terminal, same block as VSS)
```

> VSS is the HIGH-CURRENT motor power rail. It goes directly to the motor through the H-bridge.
> The L298N board can handle 7V–35V on VSS. For a 7.4V LiPo this is fine.

### 2.2 Battery to Buck Converter (Logic Power)

```
Battery (+) red wire  ──────────────────────────► Buck converter  IN+  (input positive)
Battery (-) black wire ──────────────────────────► Buck converter  IN−  (input negative)
```

> Set the buck converter output to **exactly 5.0V** by adjusting the trimmer pot while measuring
> with a multimeter between OUT+ and OUT− before connecting anything.

### 2.3 Buck Converter to ESP32

```
Buck converter  OUT+  (5V) ──────────────────────► ESP32  VIN  pin  (the 5V input pin, NOT 3.3V!)
Buck converter  OUT−  (GND) ─────────────────────► ESP32  GND  pin
```

> Do NOT connect to the ESP32's 3.3V pin — that is an OUTPUT, not an input.
> The VIN pin feeds the ESP32's onboard 3.3V regulator.

### 2.4 Buck Converter to Servo

```
Buck converter  OUT+  (5V) ──────────────────────► Servo  VCC  (Red wire)
Buck converter  OUT−  (GND) ─────────────────────► Servo  GND  (Brown or Black wire)
```

### 2.5 L298N 5V Output Pin — LEAVE UNCONNECTED

The L298N module has a small 5V output pin next to the VSS terminal. **Do not use it.**
It is noisy and can reset the ESP32 under motor load.

---

## 2B. No Buck Converter Wiring (USB-only setup)

If you do not have a buck converter, use this alternative wiring:

### Servo power (from ESP32 USB 5V)
```
ESP32  VIN  (5V from USB) ──────────────────────► Servo  VCC  (Red wire)
ESP32  GND                ──────────────────────► Servo  GND  (Brown wire)
ESP32  GPIO13             ──────────────────────► Servo  Signal
```
> The ESP32's VIN pin outputs 5V when powered by USB. A hobby servo draws ~150mA — within USB limits.
> **This only works when ESP32 is connected via USB.** For battery-only operation, get a buck converter.

### L298N logic power (self-powered from battery)
The L298N module has a built-in 5V voltage regulator (78M05) and a **"5V EN" jumper** on the board.

```
REQUIRED: 5V EN jumper must be ON (yellow jumper bridges the two pins near the 5V output)
```

When the jumper is ON, the L298N self-powers its own logic from the motor battery (VSS) through the onboard regulator. No external 5V supply needed.

> Battery must be >= 7V for the 78M05 to regulate. A 7.4V LiPo works. A 6V pack may not.

### ESP32 power
```
USB cable from PC / USB charger ──────────────────► ESP32  USB-C port
```

---

## 3. Common Ground Rail (ALL GROUNDS MUST JOIN)

This is the single most common wiring mistake. Every component's GND must connect together:

```
Battery (−)
    │
    ├──► L298N       GND  terminal
    │
    ├──► Buck conv.  IN−  / OUT−
    │
    ├──► ESP32       GND  pin
    │
    └──► Servo       GND  (Brown/Black wire)
```

Use a breadboard rail, a terminal block, or twist/solder all black wires together at one junction.

> If grounds are not common, signals will float and the motor/servo will behave erratically.

---

## 4. ESP32 to L298N Motor Driver

### 4.1 ENA Jumper — MUST BE REMOVED

The L298N board ships with a yellow jumper on the ENA header (two pins near the OUT1/OUT2 corner).

```
BEFORE:  [ENA] [●●] ← yellow jumper shorting the two pins  (DO NOT LEAVE THIS ON)
AFTER:   [ENA] [  ] ← jumper removed, two bare pins exposed
```

If the jumper is left on, ENA is permanently HIGH and the ESP32 PWM has no effect on speed.
Remove it with tweezers or fingernails.

### 4.2 Control Wires

```
ESP32  GPIO25  ──────────────────────────────────► L298N  ENA  left pin   (PWM speed control)
ESP32  GPIO26  ──────────────────────────────────► L298N  IN1  terminal
ESP32  GPIO27  ──────────────────────────────────► L298N  IN2  terminal
ESP32  GND     ──────────────────────────────────► L298N  GND  terminal   (shared ground)
```

Use short jumper wires (20cm or less). Longer wires pick up noise.

### 4.3 Motor Output Wires

```
L298N  OUT1  ────────────────────────────────────► DC Motor  terminal A  (+)
L298N  OUT2  ────────────────────────────────────► DC Motor  terminal B  (−)
```

> If motor spins backwards to what you expect, swap OUT1 and OUT2.
> Or set `MOTOR_INVERT true` in `config.h`.

### 4.4 L298N Board Layout (top view, USB of ESP32 at bottom)

```
┌──────────────────────────────────────────────┐
│ [OUT1] [OUT2]  GND  VSS(+12V)               │  ← LEFT screw terminals (motor A + power)
│                                              │
│  IN1   IN2   IN3   IN4                      │  ← signal pin header row
│ [ENA] [ ]   [ENB] [ ]                       │  ← ENA jumper ← REMOVE THIS ONE
│                                              │
│ [OUT3] [OUT4]  GND  5Vout  GND              │  ← RIGHT screw terminals (motor B - unused)
└──────────────────────────────────────────────┘
```

We only use the LEFT side (OUT1/OUT2, IN1/IN2, ENA). OUT3/OUT4, IN3/IN4, ENB are unused.

---

## 5. ESP32 to Servo

```
ESP32  GPIO13  ──────────────────────────────────► Servo  Signal  (Yellow or Orange wire)
Buck   5V out  ──────────────────────────────────► Servo  VCC     (Red wire)
Common GND     ──────────────────────────────────► Servo  GND     (Brown or Black wire)
```

### Servo Wire Colour Reference

| Servo Brand | Signal | Power | Ground |
|-------------|--------|-------|--------|
| Generic/SG90 | Orange | Red | Brown |
| Futaba | White | Red | Black |
| JR / Hitec | Yellow | Red | Black |
| Tower Pro | Yellow | Red | Black |

> The servo connector is a 3-pin female Dupont. Pin order (from left, locking tab facing up):
> **GND — VCC — Signal**

### Servo PWM Parameters (configured in firmware)

| Parameter | Value | Meaning |
|-----------|-------|---------|
| Frequency | 50 Hz | Standard hobby servo |
| Pulse center | 1500 µs | Straight ahead (trim in config.h) |
| Pulse range | ±400 µs | 1100–1900 µs = full left to full right |
| GPIO | 13 | PWM channel 2 on ESP32 |

If the servo turns the wrong way, set `STEER_INVERT true` in `config.h`.

---

## 6. ESP32 Pin Reference

```
              USB Micro-B / USB-C (bottom)
               ┌─────────────────┐
           3V3 │  ┌───────────┐  │ GND
            EN │  │  ESP32    │  │ GPIO23
       VP/IO36 │  │  WROOM-32 │  │ GPIO22
       VN/IO39 │  └───────────┘  │ TXD0/GPIO1
        GPIO34 │                 │ RXD0/GPIO3
        GPIO35 │                 │ GPIO21
        GPIO32 │                 │ GND
        GPIO33 │                 │ GPIO19
GPIO25 ►ENA    │                 │ GPIO18
GPIO26 ►IN1    │                 │ GPIO5
GPIO27 ►IN2    │                 │ GPIO17
        GPIO14 │                 │ GPIO16
        GPIO12 │                 │ GPIO4
           GND │                 │ GPIO0   ← BOOT button
GPIO13 ►SERVO  │                 │ GPIO2   ← Built-in LED
           GND │                 │ GPIO15
    5V►    VIN │                 │ SD1/GPIO8  ⚠ internal flash
        CLK/6  │                 │ SD0/GPIO7  ⚠ internal flash
        SD3/10 │                 │ SD2/GPIO9  ⚠ internal flash
        CMD/11 │                 │ GND
               └─────────────────┘
```

> ⚠ GPIO6, 7, 8, 9, 10, 11 are connected to the ESP32's internal SPI flash chip.
> **Do NOT use them** — connecting anything to these pins will crash the ESP32 or corrupt flash.

Pins in use (VisionPilot):
- **GPIO25** → L298N ENA (motor speed PWM)
- **GPIO26** → L298N IN1 (motor direction)
- **GPIO27** → L298N IN2 (motor direction)
- **GPIO13** → Servo signal
- **GPIO2**  → Built-in LED (solid=OK, fast blink=no WiFi client, slow blink=killed)
- **VIN**    → 5V from buck converter
- **GND**    → common ground (multiple GND pins available — any one works)

Safe unused pins (38-pin board has extras on the bottom rows):
- GPIO34, 35, 36(VP), 39(VN) → input-only, no internal pull-up
- GPIO0 → BOOT button (used during flashing only)
- GPIO1, 3 → TX0/RX0 (used by Serial monitor / USB)
- **GPIO6–11 → RESERVED** for internal flash, never connect anything here
- **VIN**    → 5V from buck converter
- **GND**    → common ground

---

## 7. Full Wire Table

| # | Wire | From | From Pin | To | To Pin | Suggested Colour |
|---|------|------|----------|----|--------|-----------------|
| 1 | Motor power + | Battery | + terminal | L298N | VSS screw terminal | Red (thick) |
| 2 | Motor power − | Battery | − terminal | L298N | GND (VSS block) | Black (thick) |
| 3 | Buck input + | Battery | + terminal | Buck | IN+ | Red |
| 4 | Buck input − | Battery | − terminal | Buck | IN− | Black |
| 5 | ESP32 power | Buck converter | OUT+ (5V) | ESP32 | VIN pin | Red |
| 6 | ESP32 GND | Buck converter | OUT− | ESP32 | GND pin | Black |
| 7 | Servo power | Buck converter | OUT+ (5V) | Servo | VCC (Red wire) | Red |
| 8 | Servo GND | Buck converter | OUT− | Servo | GND (Brown wire) | Black |
| 9 | Motor speed | ESP32 | GPIO25 | L298N | ENA (left pin, jumper removed) | Yellow |
| 10 | Motor dir A | ESP32 | GPIO26 | L298N | IN1 | Blue |
| 11 | Motor dir B | ESP32 | GPIO27 | L298N | IN2 | Green |
| 12 | Signal GND | ESP32 | GND | L298N | GND (signal side) | Black |
| 13 | Servo signal | ESP32 | GPIO13 | Servo | Signal (Orange wire) | Orange |
| 14 | Motor wire A | L298N | OUT1 | DC Motor | Terminal A | Blue |
| 15 | Motor wire B | L298N | OUT2 | DC Motor | Terminal B | Green |

---

## 8. Pre-Power Checklist

Check every item before connecting the battery:

- [ ] **ENA jumper removed** from L298N (two bare pins, no yellow cap)
- [ ] **Buck output = 5.0V** measured with multimeter BEFORE connecting ESP32
- [ ] **Battery polarity correct** — red to VSS+, black to GND, never reversed
- [ ] **ESP32 powered via VIN** (NOT the 3.3V pin)
- [ ] **All GNDs joined** — battery−, L298N GND, buck OUT−, ESP32 GND, servo GND
- [ ] **GPIO25 → ENA**, GPIO26 → IN1, GPIO27 → IN2 (not shifted by one pin)
- [ ] **GPIO13 → Servo signal** (yellow/orange wire, not VCC or GND)
- [ ] **No bare wires touching** each other or the PCB traces
- [ ] **Motor wires (OUT1, OUT2) not shorted** to each other

---

## 9. First Power-On Test Sequence

1. **USB only (no battery):** Connect USB cable from PC to ESP32  
   → Open Serial Monitor at **115200 baud**  
   → Should see:
   ```
   Motor self-test: FWD 500ms...
   Motor self-test: done.
   VisionPilot AP: SSID=VisionPilot  IP=192.168.4.1  port=4210
   ```

2. **Connect battery** with motor connected to OUT1/OUT2  
   → Motor should spin forward briefly (500ms self-test) then stop  
   → If motor doesn't spin → check ENA wire and battery voltage on VSS

3. **Phone WiFi:** Connect Samsung S24 to network **VisionPilot** (password: `vp123456`)

4. **Open VisionPilot app** → Status should show green **OK**

5. **Left joystick UP** → motor spins forward  
   **Left joystick DOWN** → motor spins backward  
   **Right joystick LEFT/RIGHT** → servo steers  
   Serial Monitor shows: `Motor: throttle=XX dir=FWD duty=XXX/1023 pct=XX`

---

## 10. Troubleshooting

| Symptom | Most likely cause | Fix |
|---------|-------------------|-----|
| Motor doesn't spin at all | ENA jumper still on | Remove yellow jumper from ENA |
| Motor only runs at full speed | ENA not connected to GPIO25 | Check wire from GPIO25 to ENA left pin |
| Motor spins wrong direction | OUT1/OUT2 wires swapped | Swap the two motor wires at OUT1/OUT2 |
| Servo doesn't move | Wrong GPIO pin | Check servo signal wire goes to GPIO13 |
| Servo centers but won't turn far | `STEER_RANGE_US` too low | Change to 500 in config.h, reflash |
| App shows "No signal" | Phone not on VisionPilot WiFi | Reconnect phone to VisionPilot network |
| ESP32 resets when motor starts | Buck converter too weak or GND missing | Use 5V/2A supply, check all GNDs joined |
| Motor stutters at low speed | `MOTOR_MIN_DUTY_PCT` too low | Change 35 to 45 in config.h, reflash |
| Flash fails "wrong boot mode" | BOOT sequence not correct | Hold BOOT → tap EN → release BOOT → then run flash |
| Flash drops mid-write | Samsung USB conflicting with COM5 | Unplug Samsung USB during flash, reconnect after |
