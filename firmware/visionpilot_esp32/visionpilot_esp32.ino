// VisionPilot car firmware.
// Laptop -> UDP "D,<seq>,<throttle>,<steer>" -> L298N DC motor + steering servo.
// Local safety that works even if the laptop crashes:
//   * watchdog: no drive packet for WATCHDOG_MS -> stop + centre steering
//   * bumper lock: any bumper pressed -> stop, forward refused until we reverse
//     off the obstacle (or the laptop sends "C")
//   * kill latch: "K" stops everything until "C"
// Telemetry back to laptop: "T,<lastSeq>,<bumperMask>,<battery_mV>,<state>"
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
  STATE_OK = 0,
  STATE_WATCHDOG = 1,
  STATE_BUMPER_LOCK = 2,
  STATE_KILLED = 3,
};

static const int SERVO_FREQ = 50;
static const int SERVO_BITS = 16;
static const uint32_t SERVO_PERIOD_US = 1000000UL / SERVO_FREQ;
static const int MOTOR_CH = 0;
static const int SERVO_CH = 2;  // channel 2 uses a different timer than channel 0

WiFiUDP udp;
bool udpStarted = false;
IPAddress laptopIp;
bool haveLaptop = false;

uint32_t lastDriveMs = 0;
uint32_t lastTelemMs = 0;
unsigned long lastSeq = 0;
int currentThrottle = 0;
bool killed = false;
bool bumperLock = false;
bool reversedSinceBump = false;

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
  digitalWrite(PIN_MOTOR_IN1, throttle > 0 ? HIGH : LOW);
  digitalWrite(PIN_MOTOR_IN2, throttle > 0 ? LOW : HIGH);
  pwmWrite(PIN_MOTOR_EN, MOTOR_CH, maxDuty * pct / 100);
}

void setSteer(int steer) {
  if (STEER_INVERT) steer = -steer;
  const long us = STEER_CENTER_US + (long)STEER_RANGE_US * steer / 100;
  const uint32_t duty = (uint32_t)((uint64_t)us * ((1UL << SERVO_BITS) - 1) / SERVO_PERIOD_US);
  pwmWrite(PIN_SERVO, SERVO_CH, duty);
}

void stopAll() {
  setMotor(0);
  setSteer(0);
}

// ---------- Sensors ----------
bool bumperPressed(int pin) {
  const int v = digitalRead(pin);
  return BUMPER_ACTIVE_LOW ? v == LOW : v == HIGH;
}

uint8_t readBumpers() {
  return (bumperPressed(PIN_BUMPER_L) ? 1 : 0) |
         (bumperPressed(PIN_BUMPER_C) ? 2 : 0) |
         (bumperPressed(PIN_BUMPER_R) ? 4 : 0);
}

uint32_t readBatteryMv() {
  return (uint32_t)(analogReadMilliVolts(PIN_BATTERY) * BATTERY_DIVIDER);
}

// ---------- State ----------
bool watchdogTripped() {
  return millis() - lastDriveMs > WATCHDOG_MS;
}

CarState currentState() {
  if (killed) return STATE_KILLED;
  if (bumperLock) return STATE_BUMPER_LOCK;
  if (watchdogTripped()) return STATE_WATCHDOG;
  return STATE_OK;
}

void applyDrive(int throttle, int steer) {
  if (killed) {
    stopAll();
    return;
  }
  if (bumperLock && throttle > 0) throttle = 0;
  if (bumperLock && throttle < 0) reversedSinceBump = true;
  setMotor(throttle);
  setSteer(steer);
}

void handlePacket(const char* msg) {
  if (msg[0] == 'K') {
    killed = true;
    stopAll();
    return;
  }
  if (msg[0] == 'C') {
    killed = false;
    bumperLock = false;
    return;
  }
  if (msg[0] != 'D') return;
  unsigned long seq = 0;
  int throttle = 0;
  int steer = 0;
  if (sscanf(msg, "D,%lu,%d,%d", &seq, &throttle, &steer) != 3) return;
  lastSeq = seq;
  lastDriveMs = millis();
  applyDrive(constrain(throttle, -100, 100), constrain(steer, -100, 100));
}

// ---------- Loop pieces ----------
void pollUdp() {
  int size = udp.parsePacket();
  while (size > 0) {
    char buf[64];
    const int len = udp.read(buf, sizeof(buf) - 1);
    buf[len > 0 ? len : 0] = '\0';
    laptopIp = udp.remoteIP();
    haveLaptop = true;
    handlePacket(buf);
    size = udp.parsePacket();
  }
}

void updateBumpers(uint8_t mask) {
  if (mask && !bumperLock) {
    bumperLock = true;
    reversedSinceBump = false;
    if (currentThrottle > 0) setMotor(0);
    Serial.printf("Bumper hit mask=%u -> locked\n", mask);
  }
  if (bumperLock && mask == 0 && reversedSinceBump) {
    bumperLock = false;
    Serial.println("Bumper clear after reverse -> unlocked");
  }
}

void sendTelemetry(uint8_t mask) {
  if (millis() - lastTelemMs < TELEM_INTERVAL_MS) return;
  lastTelemMs = millis();
  const IPAddress dest = haveLaptop ? laptopIp : WiFi.gatewayIP();
  char buf[64];
  const int len = snprintf(buf, sizeof(buf), "T,%lu,%u,%lu,%u", lastSeq, mask,
                           (unsigned long)readBatteryMv(), (unsigned)currentState());
  udp.beginPacket(dest, TELEM_PORT);
  udp.write((const uint8_t*)buf, len);
  udp.endPacket();
}

void updateLed() {
  const CarState s = currentState();
  uint32_t period = 200;  // fast blink: no link
  if (s == STATE_OK) {
    digitalWrite(PIN_LED, HIGH);
    return;
  }
  if (s == STATE_KILLED || s == STATE_BUMPER_LOCK) period = 1000;
  digitalWrite(PIN_LED, (millis() / (period / 2)) % 2 ? HIGH : LOW);
}

bool ensureWifi() {
  if (WiFi.status() == WL_CONNECTED) {
    if (!udpStarted) {
      udp.begin(CMD_PORT);
      udpStarted = true;
      Serial.printf("WiFi OK, car IP %s, gateway %s\n", WiFi.localIP().toString().c_str(),
                    WiFi.gatewayIP().toString().c_str());
    }
    return true;
  }
  if (udpStarted) {
    udp.stop();
    udpStarted = false;
    Serial.println("WiFi lost -> stopped");
  }
  return false;
}

void setup() {
  Serial.begin(115200);
  pinMode(PIN_LED, OUTPUT);
  pinMode(PIN_MOTOR_IN1, OUTPUT);
  pinMode(PIN_MOTOR_IN2, OUTPUT);
  const int bumperMode = BUMPER_ACTIVE_LOW ? INPUT_PULLUP : INPUT_PULLDOWN;
  pinMode(PIN_BUMPER_L, bumperMode);
  pinMode(PIN_BUMPER_C, bumperMode);
  pinMode(PIN_BUMPER_R, bumperMode);
  pwmSetup(PIN_MOTOR_EN, MOTOR_CH, MOTOR_PWM_FREQ, MOTOR_PWM_BITS);
  pwmSetup(PIN_SERVO, SERVO_CH, SERVO_FREQ, SERVO_BITS);
  stopAll();

  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);  // modem sleep adds 100ms+ latency spikes
  WiFi.setAutoReconnect(true);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  Serial.println("VisionPilot car booting, connecting WiFi...");
}

void loop() {
  const uint8_t mask = readBumpers();
  updateBumpers(mask);

  if (ensureWifi()) {
    pollUdp();
    sendTelemetry(mask);
  }
  if (watchdogTripped() && currentThrottle != 0) {
    stopAll();
    Serial.println("Watchdog -> stopped");
  }
  updateLed();
  delay(2);
}
