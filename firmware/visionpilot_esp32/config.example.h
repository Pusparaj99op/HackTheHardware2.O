// Copy this file to config.h and fill in your hotspot credentials.
// config.h is gitignored so credentials never get committed.
#pragma once

// ---- Wi-Fi mode ----
// WIFI_MODE_AP 1  → ESP32 creates its own access point (phone control, no laptop needed)
// WIFI_MODE_AP 0  → ESP32 joins your hotspot (laptop mode)
#define USE_AP_MODE 1
#define AP_SSID "VisionPilot"
#define AP_PASS "vp123456"
// In AP mode the car IP is always 192.168.4.1; phone connects to the AP above.

// ---- Wi-Fi (used only when WIFI_MODE_AP 0 — Windows Mobile Hotspot, 2.4 GHz band!) ----
#define WIFI_SSID "YOUR_HOTSPOT_NAME"
#define WIFI_PASS "YOUR_HOTSPOT_PASSWORD"

// ---- UDP ----
#define CMD_PORT 4210        // car listens here for D/K/C packets
#define TELEM_PORT 4211      // car sends T packets to the laptop on this port
#define TELEM_INTERVAL_MS 100

// ---- Safety ----
#define WATCHDOG_MS 300      // no drive packet for this long -> stop

// ---- Pins (see docs/superpowers/specs for wiring table) ----
#define PIN_MOTOR_EN 25      // L298N ENA (remove the ENA jumper)
#define PIN_MOTOR_IN1 26
#define PIN_MOTOR_IN2 27
#define PIN_SERVO 13
#define PIN_LED 2

// ---- Motor tuning ----
#define MOTOR_INVERT false   // flip if "forward" drives backwards
#define MOTOR_PWM_FREQ 1000
#define MOTOR_PWM_BITS 10
#define MOTOR_MIN_DUTY_PCT 35  // below this the toy motor just hums
#define MOTOR_MAX_DUTY_PCT 100

// ---- Steering servo tuning ----
#define STEER_INVERT false   // flip if +steer turns left
#define STEER_CENTER_US 1500 // trim so the car drives straight at steer=0
#define STEER_RANGE_US 400   // +/- microseconds at full lock

