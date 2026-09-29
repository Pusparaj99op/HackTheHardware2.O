import 'dart:convert';
import 'dart:typed_data';
import 'dart:ui';

import 'package:flutter_test/flutter_test.dart';
import 'package:visionpilot_app/car_socket.dart';
import 'package:visionpilot_app/vision_state.dart';

const _sample = {
  'type': 'state',
  'mode': 'follow',
  'modes': ['manual', 'assist', 'follow'],
  'engaged': true,
  'status': 'following bottle #5 ~1.2 m',
  'safety': null,
  'link': {'ok': true},
  'vision': {'status': 'ready | 15 fps'},
  'detections': [
    {'id': 5, 'label': 'bottle', 'conf': 0.9, 'box': [0.4, 0.4, 0.6, 0.8]},
    {'id': null, 'label': 'person', 'conf': 0.5, 'box': [0.0, 0.0, 1.0]}, // malformed box
  ],
  'labels': ['bottle', 'person'],
  'target': {'track_id': 5, 'label': 'bottle', 'point': null},
  'focus': 5,
  'phone_connected': true,
};

void main() {
  group('VisionState', () {
    test('parses a full laptop state message', () {
      final s = VisionState.tryParse(jsonEncode(_sample))!;
      expect(s.mode, 'follow');
      expect(s.engaged, isTrue);
      expect(s.carLinkOk, isTrue);
      expect(s.visionStatus, 'ready | 15 fps');
      expect(s.detections, hasLength(1)); // malformed one dropped
      expect(s.detections.first.label, 'bottle');
      expect(s.targetText, 'bottle #5');
      expect(s.focus, 5);
      expect(s.cameraConnected, isTrue);
      expect(s.modes, ['manual', 'assist', 'follow']);
    });

    test('ignores non-state and invalid messages', () {
      expect(VisionState.tryParse('not json'), isNull);
      expect(VisionState.tryParse('{"type":"error","message":"x"}'), isNull);
      expect(VisionState.tryParse('[1,2]'), isNull);
    });

    test('tolerates missing fields', () {
      final s = VisionState.tryParse('{"type":"state"}')!;
      expect(s.mode, 'manual');
      expect(s.engaged, isFalse);
      expect(s.targetText, 'no target');
      expect(s.modes, contains('assist'));
    });

    test('extracts error messages', () {
      expect(tryParseError('{"type":"error","message":"unknown mode"}'), 'unknown mode');
      expect(tryParseError('{"type":"state"}'), isNull);
      expect(tryParseError('garbage'), isNull);
    });
  });

  group('containTap', () {
    test('maps taps inside a letterboxed 16:9 image', () {
      // 16:9 image in a square box -> bars top and bottom
      const box = Size(160, 160);
      const image = Size(160, 90);
      expect(containTap(box, image, const Offset(80, 80)), const Offset(0.5, 0.5));
      expect(containTap(box, image, const Offset(0, 35)), const Offset(0, 0));
      expect(containTap(box, image, const Offset(80, 10)), isNull); // on the black bar
    });
  });

  group('jpegSize', () {
    test('reads width and height from the SOF0 header', () {
      final bytes = Uint8List.fromList([
        0xFF, 0xD8, // SOI
        0xFF, 0xE0, 0x00, 0x04, 0x00, 0x00, // APP0 (length 4)
        0xFF, 0xC0, 0x00, 0x11, 0x08, 0x01, 0x68, 0x02, 0x80, 0x03, // SOF0: 360 x 640
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
      ]);
      expect(jpegSize(bytes), const Size(640, 360));
    });

    test('returns null for non-JPEG data', () {
      expect(jpegSize(Uint8List.fromList(List.filled(20, 7))), isNull);
    });
  });

  group('CarSocket.packetFor', () {
    test('drives normally when not paused', () {
      expect(CarSocket.packetFor(paused: false, tick: 3, seq: 7, throttle: 40, steer: -20), 'D,7,40,-20');
    });

    test('only pings at 2 Hz while vision owns the car', () {
      final packets = [
        for (var t = 1; t <= 20; t++)
          CarSocket.packetFor(paused: true, tick: t, seq: t, throttle: 90, steer: 0),
      ];
      expect(packets.whereType<String>(), ['P', 'P']);
    });
  });
}
