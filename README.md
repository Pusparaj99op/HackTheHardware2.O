# 🚗🧠 VisionPilot: a vision-only self-driving RC car

A phone is the car's **eyes**, a laptop GPU is its **brain**, and an ESP32 is its **muscles**.
It uses camera vision only, like Tesla: no LiDAR.

```
📱 Phone (Chrome) ──video + gyro──► 💻 Laptop AI (YOLO11 + Depth-Anything) ──UDP 20 Hz──► 🚗 ESP32 → L298N + servo
```

## 👁️ Vision mode with the phone controller app (current setup)

```
            ESP32 Wi-Fi AP "VisionPilot" (password vp123456, car = 192.168.4.1)
   📱 Controller app (joysticks)     💻 Laptop AI brain        📱 Camera phone (Chrome)
   VISION OFF → drives car directly   silent (only pings)       -
   VISION ON  → joystick = override → laptop drives the car ←── camera video + gyro
   KILL       → straight to the car + tells the laptop
```

**Before the demo (needs internet, once):**
```powershell
cd laptop
.venv\Scripts\python tools\prefetch_models.py   # downloads YOLO + depth, prints GPU speed
```

**Every run:**
1. Power the car → the `VisionPilot` Wi-Fi appears.
2. **Laptop** joins `VisionPilot` → `cd laptop` → `.venv\Scripts\python -m visionpilot`.
   Allow Python through Windows Firewall (private network) when asked.
3. **Camera phone** joins `VisionPilot` → Chrome → the `https://192.168.4.x:8443/phone` URL printed in the terminal → *Advanced → Proceed* → **Start camera**. Mount it on the car in landscape (or hold it over the car for Hand-held mode).
4. **Controller phone** joins `VisionPilot` → open the app. The joysticks work immediately (direct mode).
5. Tap **VISION**. The app finds the laptop by itself (or use Settings → *Find laptop*). The AI video appears between the sticks.
6. Pick a mode chip:

| Mode | What it does |
|---|---|
| **Assist** | You drive with the sticks; vision **auto-brakes** before obstacles |
| **Follow** ⭐ | Tap an object in the video (or pick a class); the car follows it and stops ~0.8 m away |
| **Explore** | The car roams by itself toward open space and records its path |
| **Replay** | Re-drives a saved path (save it on the laptop dashboard) |
| **Hand-held** | Hold the camera phone over the car (ArUco marker on the roof), tap a floor spot, and the car drives there |

- **Touch a stick = instant manual override.** Let go, and vision resumes after 1 s.
- **VISION** again hands control back to the joysticks.
- **KILL** always goes straight to the car. After a KILL, press **CLEAR** to drive again.
- If the laptop drops out, the car stops (300 ms watchdog) and the app returns to direct joystick control.
- The ESP32 AP allows at most 4 devices; we use 3.

---

## Laptop-only mode (original)

| Mode | What it does |
|---|---|
| **Manual** | Drive with WASD or the on-screen pad |
| **Follow** ⭐ | Tap an object (or pick a class) and the car follows it, stopping ~0.8 m away |
| **Explore** | Wanders by itself toward open space, backs off obstacles, and records its path |
| **Replay** | Re-drives a saved path, pausing if something new blocks it |
| **Hand-held** | Hold the phone looking down at the car, tap a spot, and the car drives there around obstacles |

Safety: the car starts **KILLED**. Press **ARM** to drive, and **Space** kills it instantly. A 300 ms watchdog, 3 bumper switches and an auto-kill when all screens disconnect back that up.

---

## ✅ Setup checklist (do in order)

### 1. Wire the car (≈45 min)
| Signal | ESP32 pin |
|---|---|
| L298N **ENA** (remove its jumper!) | GPIO **25** |
| L298N IN1 / IN2 | GPIO **26** / **27** |
| Steering servo signal | GPIO **13** |
| Bumpers L / C / R (endstop SIG) | GPIO **32** / **33** / **14** |
| Battery sense (100k/47k divider), optional | GPIO **35** |

- **Power:** 2S 18650 → switch → L298N `12V` input.
- **5 V for the ESP32 + servo:** use a buck converter (LM2596). The L298N's 5 V pin is weak; if you must use it, add a 470–1000 µF cap across the servo.
- ⚠️ **All grounds connected together.**

### 2. Flash the ESP32 (≈10 min)
1. Copy `firmware/visionpilot_esp32/config.example.h` to `config.h` and put in your hotspot name and password.
2. Arduino IDE → board **ESP32 Dev Module** → upload `visionpilot_esp32.ino`.
3. Serial Monitor at 115200 should print `WiFi OK, car IP ...`.

### 3. Laptop hotspot
Windows Settings → Mobile hotspot → **Band: 2.4 GHz** (the ESP32 can't see 5 GHz) → On.

### 4. Install the laptop brain (once)
```powershell
cd laptop
uv venv --python 3.12 .venv
uv pip install --python .venv\Scripts\python.exe torch torchvision --index-url https://download.pytorch.org/whl/cu126
uv pip install --python .venv\Scripts\python.exe -r requirements.txt
```

### 5. Test the car without AI
```powershell
.venv\Scripts\python tools\drive_test.py        # W/S/A/D, Space stop, K kill, Q quit
```
✅ The car moves, and turning the hotspot off stops it within 0.3 s.
No car yet? Run `.venv\Scripts\python tools\fake_car.py` in another window instead.

### 6. Run VisionPilot
```powershell
.venv\Scripts\python -m visionpilot
```
- **Laptop:** open `https://localhost:8443/` (click *Advanced → Proceed* once).
- **Phone:** join the laptop hotspot, open the `https://192.168.137.1:8443/phone` URL printed in the terminal, tap *Advanced → Proceed* → **Start camera**.
- The first start downloads the YOLO and depth models (about 1 minute).

### 7. Calibrate (5 min, makes the map accurate)
- `tools\calibrate_speed.py`: then `set VP_SPEED_PER_PCT=<value>` before starting the server.
- On the dashboard, turn the car left by hand. If the map arrow turns the wrong way, `set VP_HEADING_SIGN=-1`.
- Follow stops too early or late? `set VP_VFOV=50` (the phone camera's vertical field of view).

### 8. Hand-held mode marker
`.venv\Scripts\python tools\print_aruco.py` → print `laptop\data\aruco_car_id0.png` (black square ≈ 12 cm) and tape it on the roof with **FRONT** toward the nose.

---

## 🎬 Demo script (3 minutes)
1. Dashboard up, phone on the car, press **ARM**.
2. **Follow:** tap the bottle in your hand → walk away → the car follows → hide it → the car stops.
3. **Explore:** the car roams the hall while the dashboard map draws its path live → **Save** the track.
4. **Replay:** put the car back at the start → **Replay** → it re-drives the path. Step in front and it pauses.
5. **Hand-held:** take the phone off, hold it over the floor, tap a spot → the car drives there around a box.
6. Press **Space**: instant stop.

## 🧯 Troubleshooting
| Problem | Fix |
|---|---|
| Phone says camera failed | Use the **https://** URL and accept the warning. Fallback: `chrome://flags` → *Insecure origins treated as secure* → add `http://192.168.137.1:8443` and run with `--no-tls` |
| Dashboard shows "car offline" | The ESP32 isn't on the hotspot (2.4 GHz?), or a firewall is blocking UDP 4211: allow Python on private networks |
| A bumper shows "pressed" all the time | Set `BUMPER_ACTIVE_LOW false` in `config.h` |
| The car drives backwards / steers reversed | `MOTOR_INVERT` / `STEER_INVERT` in `config.h` |
| The car won't go straight | Adjust `STEER_CENTER_US` in `config.h` |
| The motor hums but doesn't move | Raise `MOTOR_MIN_DUTY_PCT`, or raise the dashboard speed cap |
| Vision "degraded" | Torch/CUDA isn't installed in `.venv`; re-run step 4 |

## 🧪 Tests
```powershell
cd laptop
.venv\Scripts\python -m pytest --cov=visionpilot
```

## 📁 Layout
- `firmware/`: ESP32 sketch
- `laptop/visionpilot/`: AI brain (behaviours, safety, perception, server)
- `laptop/web/`: phone page and dashboard
- `laptop/tools/`: drive test, fake car, calibration, marker printer
- `docs/superpowers/specs/`: the design
