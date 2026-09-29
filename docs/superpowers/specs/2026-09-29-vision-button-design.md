# VisionPilot addendum: VISION button in the phone controller app (2026-09-29)

## Why
The car now runs its own Wi-Fi AP (`VisionPilot`, car `192.168.4.1`) and is driven by the Flutter
controller app (`DEMO/visionpilot_app`). The laptop vision brain (`laptop/visionpilot`) is added
**on top**: the joystick app stays the main UI, and a **VISION** button hands driving to the AI.

## Decisions (agreed with the user)
| Topic | Decision |
|---|---|
| Where AI runs | Laptop (YOLO11n + Depth-Anything-V2-S on an RTX 3050: ~14 ms each) |
| Phones | 2: the controller app in hand + a camera phone (Chrome `/phone`) on the car, or held over it |
| Joystick while vision drives | Instant takeover; vision resumes 1 s after release |
| Features | Assist (auto-brake), Follow, Explore, Replay, Hand-held |
| AI video on controller | Yes, with tap-to-target |
| Finding the laptop | UDP discovery (`VP?` → `VPL,<port>,<tls>` on port 4212) + typed IP |

## Control ownership (only one driver at a time)
- **VISION OFF:** the app sends `D` packets to the car at 20 Hz. The laptop is disengaged: it sends only `P` pings (2 Hz) to receive telemetry.
- **VISION ON:** the app sends `engage` over `wss://laptop:8443/ws/dash` and pauses its drive packets (pings only). The laptop sends `C`, then `D` packets from the active behaviour.
- **Stick input:** sent as `{"type":"manual"}` and overrides any autonomous mode. After release the laptop holds STOP until 1 s has passed, then resumes the behaviour.
- **VISION OFF again:** the app sends `release`; the laptop sends one STOP and goes silent; the app resumes direct `D`.
- **KILL:** the app sends `K` straight to the car and `kill` to the laptop, then returns to direct mode. The car stays latched until CLEAR.
- **Laptop link lost:** the app falls back to direct mode immediately. The car's 300 ms watchdog covers the gap.
- **No controller (app or dashboard) connected to the laptop while engaged:** the laptop releases the car.

## Firmware
- Peer table (2 entries: IP, last seen, **own sequence counter**).
- Telemetry `T,seq,0,0,state` goes to every peer seen in the last 2 s.
- `P` registers a peer without driving.
- Stale-packet checks are per peer, so switching drivers never drops valid packets.

## Laptop
- `ControlLoop`:
  - `engaged` flag with `engage()`, `release()` and `kill()`.
  - Standby sends pings only.
  - `_joystick_override()`.
  - `Mode.ASSIST` = manual driving + required video + the obstacle stop in the safety arbiter.
- `DiscoveryResponder` in `app.py`.
- The depth model loads from the local cache (the AP has no internet); run `tools/prefetch_models.py` beforehand.

## App
- `laptop_link.dart`: the `VisionLink` interface, `LaptopLink` (wss with a self-signed cert trusted for that host only, reconnect, discovery).
- `vision_state.dart`: pure parsing, tap mapping, JPEG size.
- `vision_panel.dart`: AI video, mode chips, target picker.
- `control_screen.dart`: VISION toggle and override timer.
- `car_socket.dart`: `paused` → pings only.

## Verification
- Laptop: `pytest` 107 tests, 91% coverage.
- App: `flutter test` 14 tests; `flutter analyze` clean.
- E2E bench script (scripted car + app + camera against the real server with GPU models):
  - disengaged → pings only;
  - discovery reply;
  - engage → C + D;
  - override D carries the stick values;
  - release / kill → no D;
  - annotated AI frame returned.
