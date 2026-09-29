import 'dart:math' as math;
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:image/image.dart' as img;
import 'package:visionpilot_app/app_role.dart';
import 'package:visionpilot_app/frame_codec.dart';
import 'package:visionpilot_app/imu_streamer.dart';

/// NV21 frame whose left half is dark and right half is bright (neutral colour).
Uint8List splitFrame(int w, int h) {
  final bytes = Uint8List(w * h * 3 ~/ 2);
  for (var y = 0; y < h; y++) {
    for (var x = 0; x < w; x++) {
      bytes[y * w + x] = x < w ~/ 2 ? 30 : 220;
    }
  }
  bytes.fillRange(w * h, bytes.length, 128); // U = V = 128 -> grey
  return bytes;
}

void main() {
  group('encodeNv21Frame', () {
    test('produces a JPEG of the frame size', () {
      final jpeg = encodeNv21Frame(Nv21Frame(width: 64, height: 48, bytes: splitFrame(64, 48)));
      final decoded = img.decodeJpg(jpeg)!;
      expect(decoded.width, 64);
      expect(decoded.height, 48);
      expect(decoded.getPixel(4, 24).r, lessThan(80));
      expect(decoded.getPixel(60, 24).r, greaterThan(170));
    });

    test('downscales wide frames to the target width, keeping aspect', () {
      final jpeg = encodeNv21Frame(Nv21Frame(width: 160, height: 120, bytes: splitFrame(160, 120), targetWidth: 80));
      final decoded = img.decodeJpg(jpeg)!;
      expect(decoded.width, 80);
      expect(decoded.height, 60);
    });

    test('rotate180 swaps the dark and bright halves', () {
      final jpeg = encodeNv21Frame(
        Nv21Frame(width: 64, height: 48, bytes: splitFrame(64, 48), rotate180: true),
      );
      final decoded = img.decodeJpg(jpeg)!;
      expect(decoded.getPixel(4, 24).r, greaterThan(170));
      expect(decoded.getPixel(60, 24).r, lessThan(80));
    });

    test('rejects a truncated buffer', () {
      expect(
        () => encodeNv21Frame(Nv21Frame(width: 64, height: 48, bytes: Uint8List(10))),
        throwsArgumentError,
      );
    });
  });

  group('buildImuSample', () {
    test('matches the browser devicemotion format (alpha=z, beta=x, gamma=y, deg/s)', () {
      final s = buildImuSample(
        tMs: 1500,
        gyroX: math.pi,
        gyroY: math.pi / 2,
        gyroZ: math.pi / 4,
        accelX: 0.1,
        accelY: 0.2,
        accelZ: 9.8,
      );
      expect(s[0], 1500);
      final rates = s[1] as List<double>;
      expect(rates[0], closeTo(45, 1e-9)); // alpha = z
      expect(rates[1], closeTo(180, 1e-9)); // beta = x
      expect(rates[2], closeTo(90, 1e-9)); // gamma = y
      expect(s[2], [0.1, 0.2, 9.8]);
    });
  });

  group('AppRole', () {
    test('parses saved names and defaults to controller', () {
      expect(AppRole.parse('camera'), AppRole.camera);
      expect(AppRole.parse('both'), AppRole.both);
      expect(AppRole.parse(null), AppRole.controller);
      expect(AppRole.parse('nonsense'), AppRole.controller);
    });

    test('only the camera role stays off the car', () {
      expect(AppRole.camera.drivesCar, isFalse);
      expect(AppRole.controller.drivesCar, isTrue);
      expect(AppRole.both.drivesCar, isTrue);
      expect(AppRole.controller.streamsCamera, isFalse);
      expect(AppRole.both.streamsCamera, isTrue);
    });
  });
}
