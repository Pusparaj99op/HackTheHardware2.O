import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:visionpilot_app/car_socket.dart';
import 'package:visionpilot_app/control_screen.dart';
import 'package:visionpilot_app/joystick_widget.dart';
import 'package:visionpilot_app/laptop_link.dart';
import 'package:visionpilot_app/vision_state.dart';

class FakeLink implements VisionLink {
  final sent = <Map<String, Object?>>[];
  bool disposed = false;
  final stateCtrl = StreamController<VisionState>.broadcast();

  @override
  final ValueNotifier<bool> connected = ValueNotifier<bool>(true);

  @override
  Stream<VisionState> get states => stateCtrl.stream;

  @override
  Stream<Uint8List> get frames => const Stream.empty();

  @override
  Stream<String> get errors => const Stream.empty();

  @override
  void send(Map<String, Object?> message) => sent.add(message);

  @override
  void dispose() => disposed = true;

  bool sentType(String type) => sent.any((m) => m['type'] == type);
}

/// Lets the async VISION toggle finish (connector future + rebuild).
Future<void> settle(WidgetTester tester) async {
  await tester.pump();
  await tester.pump();
}

Future<void> pumpScreen(WidgetTester tester, CarSocket socket, VisionConnector connect) async {
  tester.view.physicalSize = const Size(2400, 1080);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: ControlScreen(socket: socket, carIp: '192.168.4.1', connectVision: connect),
  ));
}

void main() {
  testWidgets('VISION hands the car to the laptop and back', (tester) async {
    final socket = CarSocket();
    final link = FakeLink();
    await pumpScreen(tester, socket, () async => link);

    await tester.tap(find.byKey(const Key('vision-toggle')));
    await settle(tester);
    expect(socket.paused, isTrue);
    expect(link.sentType('engage'), isTrue);
    expect(find.text('VISION ON'), findsOneWidget);

    await tester.tap(find.byKey(const Key('vision-toggle')));
    await settle(tester);
    expect(link.sentType('release'), isTrue);
    expect(socket.paused, isFalse);
    expect(link.disposed, isTrue);
  });

  testWidgets('KILL during vision tells the laptop and returns joystick control', (tester) async {
    final socket = CarSocket();
    final link = FakeLink();
    await pumpScreen(tester, socket, () async => link);
    await tester.tap(find.byKey(const Key('vision-toggle')));
    await settle(tester);

    await tester.tap(find.text('KILL'));
    await settle(tester);
    expect(link.sentType('kill'), isTrue);
    expect(link.sentType('release'), isFalse);
    expect(socket.paused, isFalse);
  });

  testWidgets('laptop link lost falls back to direct control', (tester) async {
    final socket = CarSocket();
    final link = FakeLink();
    await pumpScreen(tester, socket, () async => link);
    await tester.tap(find.byKey(const Key('vision-toggle')));
    await settle(tester);

    link.connected.value = false;
    await settle(tester);
    expect(socket.paused, isFalse);
    expect(find.textContaining('Laptop lost'), findsOneWidget);
  });

  testWidgets('missing laptop shows a hint and keeps direct control', (tester) async {
    final socket = CarSocket();
    await pumpScreen(tester, socket, () async => null);
    await tester.tap(find.byKey(const Key('vision-toggle')));
    await settle(tester);
    expect(find.textContaining('Laptop not found'), findsOneWidget);
    expect(socket.paused, isFalse);
  });

  testWidgets('holding a joystick during vision sends a manual override', (tester) async {
    final socket = CarSocket();
    final link = FakeLink();
    await pumpScreen(tester, socket, () async => link);
    await tester.tap(find.byKey(const Key('vision-toggle')));
    await settle(tester);

    final stick = tester.getCenter(find.byType(JoystickWidget).first);
    final gesture = await tester.startGesture(stick + const Offset(0, 25));
    await gesture.moveBy(const Offset(0, -60));
    await tester.pump(const Duration(milliseconds: 120));
    final overrides = link.sent.where((m) => m['type'] == 'manual').toList();
    expect(overrides, isNotEmpty);
    expect(overrides.last['throttle'] as int, greaterThan(0));
    await gesture.up();
    await settle(tester);
  });
}
