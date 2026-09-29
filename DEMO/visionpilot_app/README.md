# VisionPilot phone app

Drive the VisionPilot car, or use the phone as the car's camera for the laptop vision brain.

## Roles (Settings -> Role)

| Role | Screen | What it does |
|------|--------|--------------|
| Controller | landscape | Two joysticks drive the car over UDP. VISION hands driving to the laptop and shows its annotated video. |
| Controller + Camera | landscape | Same, but this phone's back camera is the car's eyes (local preview with boxes). |
| Camera | **portrait** | Phone is mounted on the car. Streams camera + gyro to the laptop. Switch-camera button (back/front, remembered), mode chips, big KILL. Never drives the car itself. |

## Setup

1. Power the car. Its Wi-Fi is **VisionPilot** (car at `192.168.4.1`).
2. Join **both** the phone and the laptop to the VisionPilot Wi-Fi.
3. On the laptop: `cd laptop && .venv/Scripts/python -m visionpilot`.
4. Open the app. The laptop is found automatically. If it isn't found, go to Settings -> Find laptop or type its IP.

## Demo checklist

- [ ] Laptop and phone are both on VisionPilot Wi-Fi.
- [ ] The top bar shows **OK** in Controller mode, or **LIVE** in Camera mode.
- [ ] The joysticks move the car.
- [ ] VISION ON shows video and `AI: ready`.
- [ ] Tap a box to target it, then pick Follow.
- [ ] KILL stops the car. It is sent to both the laptop and the car.
- [ ] Camera role: the video is upright on the laptop for both lenses.

## Dev

```
flutter analyze && flutter test
flutter build apk --release
adb install -r build/app/outputs/flutter-apk/app-release.apk
```

Without the shared Wi-Fi (USB only): `adb reverse tcp:8443 tcp:8443`, then set the laptop IP to `127.0.0.1`.
