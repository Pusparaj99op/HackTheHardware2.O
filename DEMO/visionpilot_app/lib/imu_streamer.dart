import 'dart:async';
import 'dart:math' as math;

import 'package:sensors_plus/sensors_plus.dart';

const _radToDeg = 180 / math.pi;
const maxImuBatch = 200; // the laptop rejects bigger batches

/// One IMU sample in the exact format the browser camera page sends:
/// `[t_ms, [alpha, beta, gamma] deg/s, [ax, ay, az] m/s²]` where alpha/beta/gamma
/// are the rotation rates about the device z / x / y axes.
List<Object> buildImuSample({
  required double tMs,
  required double gyroX,
  required double gyroY,
  required double gyroZ,
  required double accelX,
  required double accelY,
  required double accelZ,
}) =>
    [
      tMs,
      [gyroZ * _radToDeg, gyroX * _radToDeg, gyroY * _radToDeg],
      [accelX, accelY, accelZ],
    ];

/// Streams phone gyro + gravity to the laptop (heading for path memory).
class ImuStreamer {
  static const _flushPeriod = Duration(milliseconds: 100);

  final void Function(Map<String, Object?> message) send;
  final _buffer = <List<Object>>[];
  var _accel = const [0.0, 0.0, 9.81];
  StreamSubscription<GyroscopeEvent>? _gyroSub;
  StreamSubscription<AccelerometerEvent>? _accelSub;
  Timer? _flush;

  ImuStreamer(this.send);

  void start() {
    _accelSub =
        accelerometerEventStream(samplingPeriod: SensorInterval.gameInterval)
            .listen((e) => _accel = [e.x, e.y, e.z], onError: (_) {});
    _gyroSub = gyroscopeEventStream(samplingPeriod: SensorInterval.gameInterval)
        .listen(
      (e) => _buffer.add(buildImuSample(
        tMs: e.timestamp.microsecondsSinceEpoch / 1000,
        gyroX: e.x,
        gyroY: e.y,
        gyroZ: e.z,
        accelX: _accel[0],
        accelY: _accel[1],
        accelZ: _accel[2],
      )),
      onError: (_) {}, // phone without a gyro: heading just stays constant
    );
    _flush = Timer.periodic(_flushPeriod, (_) => _send());
  }

  void _send() {
    if (_buffer.isEmpty) return;
    final start =
        _buffer.length > maxImuBatch ? _buffer.length - maxImuBatch : 0;
    final batch = _buffer.sublist(start);
    _buffer.clear();
    send({'type': 'imu', 'samples': batch});
  }

  void stop() {
    _flush?.cancel();
    _gyroSub?.cancel();
    _accelSub?.cancel();
    _buffer.clear();
  }
}
