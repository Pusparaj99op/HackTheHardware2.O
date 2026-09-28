# 🚗🧠 VisionPilot — a "Tesla-style" AI RC Car (HackTheHardware 2.0, 12h solo build)

## Context
- **Why:** Hackathon project. Turn an RC-car chassis into a car that drives itself using **camera vision only**, in the spirit of Tesla's vision-only approach.
- **Starting point:** The repo is empty (only `images/`). The parts on hand are in the photos.
- **Constraints:** 12 hours, solo + Claude Code, Android phone (Chrome), RTX laptop, venue = large hall/corridor, laptop hotspot network.
- **Outcome:** A phone streams video to the laptop, the laptop runs the AI and decides, and an ESP32 on the car drives it.
  - The car **follows** objects.
  - It **remembers and replays its path** on a live admin dashboard.
  - It **explores on its own** while avoiding obstacles.
  - In **hand-held mode** the phone watches the car from outside and steers it to a tapped target.

### Decisions locked with the user
| Topic | Decision |
|---|---|
| Data path | Phone → Laptop (AI) → ESP32 (car) |
| Phone | 1 Android phone, **two roles**: mounted on the car (eyes) OR in hand/on a stand (watching the car from outside) |
| Priority | ① Follow → ② Path memory + Auto-explore → (natural-language/VLM **dropped**) |
| Follow target | Pick a YOLO class from a dropdown **and** tap-to-track on the phone or dashboard video |
| Drivetrain | Existing rear DC motor via **L298N** + existing **steering servo** (28BYJ-48 steppers not used: too slow, ~5 cm/s) |
| Power | 2S 18650 (7.4–8.4 V) |
| Safety | Vision distance + **3 endstop switches as bumpers** + **dashboard kill switch** + **300 ms watchdog** |
| Car self-detection (hand mode) | Printed **ArUco marker** on the roof |
| Odometry | Phone gyro heading + calibrated speed, **plus visual optical flow** |
| Stack | Python (FastAPI, OpenCV, Ultralytics YOLO on CUDA, Depth-Anything-V2-Small) + one web app (phone page + dashboard); ESP32 in Arduino C++ |
| Phone app | Browser page first; native app later (after the demo works) |

## Approaches considered → chosen
1. **Laptop-brain, phone as a browser sensor (CHOSEN).** A single Python codebase serves both the phone page and the dashboard. The RTX GPU runs YOLO and depth together. Nothing to install on the phone.
2. Native Android app streaming over WebRTC: better latency but costs ~3 hours. Deferred to the "later" phase.
3. AI running on the phone, talking to the ESP32 directly: can't run YOLO + depth + dashboard well. Rejected.

## Architecture
```
 📱 Android Chrome  ──HTTPS WebSocket (JPEG 640x360 @15fps + gyro + taps)──►  💻 Laptop (FastAPI)
   /phone page                                                                  ├─ perception: YOLO11 + ByteTrack, Depth-Anything-V2-S, ArUco
                                                                                ├─ odometry: phone heading + speed model + optical flow
 🖥️ Dashboard  ◄──WebSocket (annotated video, map, telemetry)──────────────────┤─ behaviors: MANUAL / FOLLOW / EXPLORE / REPLAY / HANDHELD
   localhost:8000                                                               ├─ safety arbiter (kill, bumper, watchdog, too-close)
                                                                                └─ car_link: UDP 20 Hz ─► 🚗 ESP32 (192.168.137.x)
 🚗 ESP32 ──UDP telemetry (bumpers, seq, battery V)──► laptop                         L298N → DC motor, servo, 3 bumpers
```
- **Car protocol (UDP, port 4210):**
  - Laptop sends `D,<seq>,<throttle -100..100>,<steer -100..100>` and `K` (kill).
  - ESP32 replies `T,<seq>,<bumperMask>,<battery_mV>`.
  - The laptop is always at `192.168.137.1` (Windows hotspot gateway), so the ESP32 needs no configuration.
- **ESP32 local safety (works even if the laptop dies):**
  - No valid packet for 300 ms → stop and centre the steering.
  - A bumper press → stop and refuse forward motion until the laptop sends a reverse or clear command.
- **Safety arbiter on the laptop:** every behaviour's output goes through `safety.py`. Priority order: kill > bumper > watchdog/stale video > obstacle-too-close > behaviour. Speed is capped at 40% PWM by default, adjustable on the dashboard.

## Modes (behaviours)
1. **MANUAL:** WASD or on-screen joystick on the dashboard. Always available as a fallback.
2. **FOLLOW (car-mounted phone):**
   - YOLO + ByteTrack gives stable track IDs. The target is set by class dropdown or by tapping (phone or dashboard). The tap picks the track ID under the finger.
   - Steering is proportional to the target's horizontal offset.
   - Distance is estimated from bounding-box height (per-class reference height, calibratable). Throttle comes from the distance error, and the car stops at 0.8 m.
   - Target lost for more than 0.7 s → stop and show "searching".
   - Any other detection that is large and low in the centre of the frame → stop.
3. **Path memory + REPLAY:**
   - Every mode logs poses `(x, y, θ, t)`.
     - `θ` comes from the phone's gyro (relative `deviceorientation`, not the magnetic compass, which steel in the hall would disturb).
     - Distance comes from a calibrated `speed = k·throttle`, corrected by optical flow (flow ≈ 0 while throttling means stuck or blocked).
   - The dashboard map shows the trail, the current pose arrow, bumper-hit marks, and saved tracks (JSON in `data/tracks/`).
   - Replay uses pure-pursuit over the saved poses. Vision stays on the whole time: a new obstacle → pause and alert, resume when clear.
4. **AUTO-EXPLORE:**
   - Depth-Anything-V2-Small gives relative depth. The lower 60% of the frame is split into 5 columns, and the car steers toward the most open one.
   - Blocked everywhere or bumper hit → reverse 0.6 s and turn.
   - The trail records automatically, so the car "builds its map".
5. **HANDHELD (phone in hand or on a stand, watching the scene):**
   - ArUco gives the car's pixel position and heading every frame.
   - The target is a tapped point or a tapped object. YOLO boxes count as obstacles.
   - The desired direction is the pull toward the target plus the push away from obstacles. Steering follows the heading error. Low constant speed; stop within radius.
   - Stretch goal: a 4-tap floor homography for metric accuracy.

## Hardware wiring (ESP32 DevKit)
| Signal | ESP32 pin | Notes |
|---|---|---|
| L298N ENA (PWM speed) | GPIO25 | Remove the ENA jumper |
| L298N IN1 / IN2 | GPIO26 / GPIO27 | Direction |
| Steering servo signal | GPIO13 | ESP32Servo lib, 50 Hz |
| Bumper L / C / R (endstop NO→GND) | GPIO32 / 33 / 14 | `INPUT_PULLUP`, debounced |
| Battery sense (100k/47k divider) | GPIO35 | Optional, ADC1 |
| Status LED | GPIO2 | Blink pattern = state |
- **Power:** 2S 18650 → switch → L298N 12V terminal. For the 5 V to the ESP32 and servo, prefer an **LM2596/MP1584 buck converter**. The L298N's own 5 V regulator (~0.5 A) can brown out when the servo stalls. If no buck is available, put 470–1000 µF across the servo supply. **Common ground everywhere.**
- The phone mounts at the front in landscape (clamp or rubber bands) for car-mounted mode.
- ⚠️ The **ESP32 only does 2.4 GHz**, so set the Windows hotspot band to **2.4 GHz**.
- 🛒 Buy or check: buck converter, 470 µF capacitor, 2S holder + switch, phone clamp, print an ArUco marker (DICT_4X4_50 id 0, ~12 cm). Optional cheap upgrade: HC-SR04.

## Repo layout (new files; each under ~400 lines)
```
docs/superpowers/specs/2026-09-28-visionpilot-design.md   ← this design, written first
firmware/visionpilot_esp32/visionpilot_esp32.ino, config.h (Wi-Fi creds via config.h, gitignored template)
laptop/requirements.txt
laptop/visionpilot/
  main.py            FastAPI app, static files, /ws/phone, /ws/dash
  config.py          all tunables (speed cap, stop distance, gains, ports)
  car_link.py        UDP send loop 20 Hz, telemetry parse, link-alive
  protocol.py        encode/decode car packets (pure, tested)
  safety.py          arbiter (pure, tested)
  odometry.py        heading + speed model + flow fusion (pure core, tested)
  path_memory.py     record/save/load/downsample tracks (pure, tested)
  control.py         mode state machine, 20 Hz loop
  perception/detector.py   YOLO11n/s + ByteTrack, tap→track-id
  perception/depth.py      Depth-Anything-V2-Small → 5-column openness
  perception/aruco.py      car pose from marker
  perception/flow.py       optical-flow motion magnitude
  behaviors/{manual,follow,explore,replay,handheld}.py  (pure controllers, tested)
laptop/web/phone.html, phone.js, dashboard.html, dashboard.js, map.js, style.css
laptop/tests/…               pytest for protocol, safety, controllers, odometry, path_memory
tools/make_cert.py (self-signed HTTPS), print_aruco.py, calibrate_speed.py, drive_test.py
```
- **HTTPS:** Android Chrome needs a secure origin for the camera and gyro. Use a self-signed cert from `tools/make_cert.py` (tap "proceed" once). Fallback: the Chrome flag `unsafely-treat-insecure-origin-as-secure` for `http://192.168.137.1:8000`.

## 12-hour timeline (always keep something demoable; commit + tag at each ✅)
| Time | Milestone | ✅ Done when |
|---|---|---|
| 0:00–0:20 | Write the spec doc + skeleton repo, `.gitignore` | Spec committed |
| 0:20–1:15 | **M0** wiring + ESP32 firmware (UDP drive, watchdog, bumpers) + `tools/drive_test.py` | The car drives from the laptop keyboard; unplugging Wi-Fi stops it within 300 ms |
| 1:15–2:30 | **M1** FastAPI server, phone page streaming camera + gyro, dashboard with live video, manual drive, **big KILL button (space bar)** | Phone camera visible on the laptop; drive via the dashboard |
| 2:30–4:30 | **M2 FOLLOW:** YOLO + tracking, class dropdown, tap-to-track (phone + dashboard), distance estimate, obstacle stop | ⭐ **Core demo works.** Tag `v0.1-follow` |
| 4:30–6:30 | **M3** odometry + live map trail + save/load + REPLAY with vision pause | The recorded path redraws and replays roughly |
| 6:30–8:30 | **M4 AUTO-EXPLORE:** depth openness steering + bumper recovery | Wanders the hall 2+ minutes without getting stuck |
| 8:30–10:00 | **M5 HANDHELD:** ArUco car pose + go-to-tapped target around obstacles | The car drives to a tapped spot while the phone is held |
| 10:00–11:00 | Buffer: tuning, optical-flow fusion, polish | — |
| 11:00–12:00 | **Freeze:** README, demo script, charged batteries, fallback plan (MANUAL) | Full rehearsal done |

**If behind schedule, cut in this order:** HANDHELD → optical flow → REPLAY (keep the map drawing) → EXPLORE. FOLLOW + MANUAL + KILL are never cut.

## Testing / verification
- **TDD (pytest) for pure logic:** protocol encode/decode, the safety arbiter priority table, the follow controller (offset→steer, distance→throttle, lost→stop), explore column choice, pure-pursuit, odometry integration, path save/load. Target 80%+ on these modules: `pytest --cov=visionpilot`.
- **Hardware checks (manual, each milestone):**
  1. `tools/drive_test.py`: forward, reverse, left, right respond; kill stops instantly.
  2. Watchdog: turn the hotspot off mid-drive → the car stops.
  3. Press each bumper → the car stops and refuses forward; the dashboard shows which bumper.
  4. Dashboard FPS/latency readout: phone→laptop→command under ~200 ms.
  5. FOLLOW: walk away with a bottle → the car follows and stops about 0.8 m from it; hide the bottle → it stops.
  6. REPLAY: drive an L-shape manually → replay → the end point is within ~0.5 m.
  7. EXPLORE: 2 minutes in the corridor without a hard crash; the trail draws on the map.
  8. HANDHELD: phone on a stand, tap a floor spot → the car reaches it while avoiding a box.
- Code review pass (code-reviewer agent) after M2 and before the freeze.

## Later (after the demo works — user asked)
- Native Android app (Kotlin or Flutter) replacing the browser phone page, with WebRTC video.
- HC-SR04 or LiDAR as a second safety sensor; wheel encoder for true odometry.
- Natural-language / VLM commands (dropped for now).
