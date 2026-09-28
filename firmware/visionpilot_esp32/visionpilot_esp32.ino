// VisionPilot car firmware — simplified: WiFi AP + L298N motor + servo only.
// Phone -> UDP "D,<seq>,<throttle>,<steer>" -> L298N DC motor + steering servo.
// Safety: watchdog (no packet for WATCHDOG_MS -> stop), kill latch (K/C).
// Telemetry: "T,<lastSeq>,0,0,<state>" back to phone on port 4211.
#include <WiFi.h>
#include <WiFiUdp.h>
#if __has_include(<esp_arduino_version.h>)
#include <esp_arduino_version.h>
#endif
#include "config.h"

#ifndef ESP_ARDUINO_VERSION_MAJOR
#define ESP_ARDUINO_VERSION_MAJOR 2
#endif

enum CarState : uint8_t {
  STATE_OK       = 0,
  STATE_WATCHDOG = 1,
  STATE_KILLED   = 3,
};

static const int SERVO_FREQ      = 50;
static const int SERVO_BITS      = 16;
static const uint32_t SERVO_PERIOD_US = 1000000UL / SERVO_FREQ;
static const int MOTOR_CH        = 0;
static const int SERVO_CH        = 2;
static const unsigned long SEQ_RESTART_GAP = 1000;

WiFiUDP udp;
bool udpStarted  = false;
IPAddress laptopIp;
bool haveLaptop  = false;

uint32_t lastDriveMs  = 0;
uint32_t lastTelemMs  = 0;
unsigned long lastSeq = 0;
int currentThrottle   = 0;
bool killed           = false;

// ---------- PWM helpers (Arduino-ESP32 core 2.x and 3.x) ----------
void pwmSetup(int pin, int ch, int freq, int bits) {
#if ESP_ARDUINO_VERSION_MAJOR >= 3
  ledcAttachChannel(pin, freq, bits, ch);
#else
  ledcSetup(ch, freq, bits);
  ledcAttachPin(pin, ch);
#endif
}

void pwmWrite(int pin, int ch, uint32_t duty) {
#if ESP_ARDUINO_VERSION_MAJOR >= 3
  (void)ch;
  ledcWrite(pin, duty);
#else
  (void)pin;
  ledcWrite(ch, duty);
#endif
}

// ---------- Actuators ----------
void setMotor(int throttle) {
  currentThrottle = throttle;
  if (MOTOR_INVERT) throttle = -throttle;
  if (throttle == 0) {
    digitalWrite(PIN_MOTOR_IN1, LOW);
    digitalWrite(PIN_MOTOR_IN2, LOW);
    pwmWrite(PIN_MOTOR_EN, MOTOR_CH, 0);
    return;
  }
  const uint32_t maxDuty = (1UL << MOTOR_PWM_BITS) - 1;
  const int mag = abs(throttle);
  const int pct = MOTOR_MIN_DUTY_PCT + (MOTOR_MAX_DUTY_PCT - MOTOR_MIN_DUTY_PCT) * (mag - 1) / 99;
  const uint32_t duty = maxDuty * pct / 100;
  digitalWrite(PIN_MOTOR_IN1, throttle > 0 ? HIGH : LOW);
  digitalWrite(PIN_MOTOR_IN2, throttle > 0 ? LOW  : HIGH);
  pwmWrite(PIN_MOTOR_EN, MOTOR_CH, duty);
  Serial.printf("Motor: throttle=%d dir=%s duty=%lu/%lu pct=%d\n",
                throttle, throttle > 0 ? "FWD" : "REV", (unsigned long)duty,
                (unsigned long)maxDuty, pct);
}

void setSteer(int steer) {
  if (STEER_INVERT) steer = -steer;
  const long us   = STEER_CENTER_US + (long)STEER_RANGE_US * steer / 100;
  const uint32_t duty = (uint32_t)((uint64_t)us * ((1UL << SERVO_BITS) - 1) / SERVO_PERIOD_US);
  pwmWrite(PIN_SERVO, SERVO_CH, duty);
}

void stopAll() {
  setMotor(0);
  setSteer(0);
}

// ---------- State ----------
bool watchdogTripped() {
  return millis() - lastDriveMs > WATCHDOG_MS;
}

CarState currentState() {
  if (killed)            return STATE_KILLED;
  if (watchdogTripped()) return STATE_WATCHDOG;
  return STATE_OK;
}

void applyDrive(int throttle, int steer) {
  if (killed) { stopAll(); return; }
  setMotor(throttle);
  setSteer(steer);
}

void handlePacket(const char* msg) {
  if (msg[0] == 'K') { killed = true;  stopAll(); return; }
  if (msg[0] == 'C') { killed = false; return; }
  if (msg[0] != 'D') return;

  unsigned long seq = 0;
  int throttle = 0, steer = 0;
  if (sscanf(msg, "D,%lu,%d,%d", &seq, &throttle, &steer) != 3) return;

  const bool stale = !watchdogTripped() && seq <= lastSeq && lastSeq - seq < SEQ_RESTART_GAP;
  if (stale) return;

  lastSeq      = seq;
  lastDriveMs  = millis();
  applyDrive(constrain(throttle, -100, 100), constrain(steer, -100, 100));
}

// ---------- Loop pieces ----------
void pollUdp() {
  int size = udp.parsePacket();
  while (size > 0) {
    char buf[64];
    const int len = udp.read(buf, sizeof(buf) - 1);
    buf[len > 0 ? len : 0] = '\0';
    laptopIp  = udp.remoteIP();
    haveLaptop = true;
    handlePacket(buf);
    size = udp.parsePacket();
  }
}

void sendTelemetry() {
  if (millis() - lastTelemMs < TELEM_INTERVAL_MS) return;
  lastTelemMs = millis();
  const IPAddress dest = haveLaptop ? laptopIp : WiFi.softAPIP();
  char buf[64];
  // Keep 5-field format compatible with existing app: T,seq,mask,mV,state
  const int len = snprintf(buf, sizeof(buf), "T,%lu,0,0,%u", lastSeq, (unsigned)currentState());
  udp.beginPacket(dest, TELEM_PORT);
  udp.write((const uint8_t*)buf, len);
  udp.endPacket();
}

void updateLed() {
  if (currentState() == STATE_OK) { digitalWrite(PIN_LED, HIGH); return; }
  const uint32_t period = (currentState() == STATE_KILLED) ? 1000 : 200;
  digitalWrite(PIN_LED, (millis() / (period / 2)) % 2 ? HIGH : LOW);
}

bool ensureWifi() {
#if USE_AP_MODE
  return udpStarted;
#else
  if (WiFi.status() == WL_CONNECTED) {
    if (!udpStarted) {
      udp.begin(CMD_PORT);
      udpStarted = true;
      Serial.printf("WiFi OK, car IP %s\n", WiFi.localIP().toString().c_str());
    }
    return true;
  }
  if (udpStarted) { udp.stop(); udpStarted = false; }
  return false;
#endif
}

void setup() {
  Serial.begin(115200);
  pinMode(PIN_LED,       OUTPUT);
  pinMode(PIN_MOTOR_IN1, OUTPUT);
  pinMode(PIN_MOTOR_IN2, OUTPUT);

  pwmSetup(PIN_MOTOR_EN, MOTOR_CH, MOTOR_PWM_FREQ, MOTOR_PWM_BITS);
  pwmSetup(PIN_SERVO,    SERVO_CH, SERVO_FREQ,      SERVO_BITS);
  stopAll();

  // Brief motor pulse to confirm H-bridge wiring (500ms at 50% both directions)
  Serial.println("Motor self-test: FWD 500ms...");
  digitalWrite(PIN_MOTOR_IN1, HIGH);
  digitalWrite(PIN_MOTOR_IN2, LOW);
  pwmWrite(PIN_MOTOR_EN, MOTOR_CH, ((1UL << MOTOR_PWM_BITS) - 1) * 50 / 100);
  delay(500);
  stopAll();
  Serial.println("Motor self-test: done.");

#if USE_AP_MODE
  WiFi.mode(WIFI_AP);
  WiFi.softAP(AP_SSID, AP_PASS);
  udp.begin(CMD_PORT);
  udpStarted = true;
  Serial.printf("VisionPilot AP: SSID=%s  IP=%s  port=%d\n",
                AP_SSID, WiFi.softAPIP().toString().c_str(), CMD_PORT);
#else
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  WiFi.setAutoReconnect(true);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  Serial.println("VisionPilot booting, connecting WiFi...");
#endif
}

void loop() {
  if (ensureWifi()) {
    pollUdp();
    sendTelemetry();
  }
  if (watchdogTripped() && currentThrottle != 0) {
    stopAll();
    Serial.println("Watchdog -> stopped");
  }
  updateLed();
  delay(2);
}
