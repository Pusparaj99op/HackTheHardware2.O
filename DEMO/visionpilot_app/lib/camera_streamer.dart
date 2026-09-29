import 'dart:async';

import 'package:camera/camera.dart';
import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'frame_codec.dart';
import 'imu_streamer.dart';
import 'laptop_link.dart';

/// This phone as the car's eyes: back camera + gyro streamed to the laptop over /ws/phone.
///
/// Frames are NV21 from CameraX, converted to ~640 px JPEG in a background
/// isolate at ~10 fps (frames are dropped while one is still encoding, so
/// latency never builds up).
class CameraSession {
  static const _minFrameGap = Duration(milliseconds: 100);
  static const rotateKey = 'camera_rotate180';

  CameraController? controller;
  LaptopLink? link;
  ImuStreamer? _imu;
  bool rotate180 = false;
  bool _encoding = false;
  DateTime _lastFrame = DateTime.fromMillisecondsSinceEpoch(0);
  bool _closed = false;

  /// Short human-readable status for the UI.
  final status = ValueNotifier<String>('starting camera...');

  /// Frames actually sent in the last second (shown in the UI).
  final fps = ValueNotifier<int>(0);
  int _sentThisSecond = 0;
  Timer? _fpsTimer;

  Future<void> start() async {
    final prefs = await SharedPreferences.getInstance();
    rotate180 = prefs.getBool(rotateKey) ?? false;
    await _startCamera();
    if (_closed) return;
    await connectLaptop(prefs);
  }

  Future<void> _startCamera() async {
    final cameras = await availableCameras();
    if (cameras.isEmpty) throw CameraException('no-camera', 'This phone has no camera');
    final back = cameras.firstWhere(
      (c) => c.lensDirection == CameraLensDirection.back,
      orElse: () => cameras.first,
    );
    final cam = CameraController(
      back,
      ResolutionPreset.medium,
      enableAudio: false,
      imageFormatGroup: ImageFormatGroup.nv21,
    );
    await cam.initialize(); // asks for camera permission the first time
    if (_closed) {
      await cam.dispose();
      return;
    }
    controller = cam;
    await cam.startImageStream(_onImage);
    _fpsTimer = Timer.periodic(const Duration(seconds: 1), (_) {
      fps.value = _sentThisSecond;
      _sentThisSecond = 0;
    });
  }

  /// Connects (or reconnects) the /ws/phone channel; true when connected.
  Future<bool> connectLaptop([SharedPreferences? prefs]) async {
    final p = prefs ?? await SharedPreferences.getInstance();
    status.value = 'finding laptop...';
    link?.dispose();
    link = await LaptopLink.findAndConnect(
      savedIp: p.getString('laptop_ip'),
      savedPort: p.getInt('laptop_port') ?? 8443,
      path: '/ws/phone',
    );
    final current = link;
    if (current == null) {
      status.value = 'laptop not found - check Wi-Fi / server';
      return false;
    }
    await p.setString('laptop_ip', current.host);
    await p.setInt('laptop_port', current.port);
    status.value = 'streaming to ${current.host}';
    _imu?.stop();
    _imu = ImuStreamer(current.send)..start();
    return true;
  }

  void _onImage(CameraImage image) {
    final current = link;
    final now = DateTime.now();
    if (_closed || _encoding || current == null || !current.connected.value) return;
    if (now.difference(_lastFrame) < _minFrameGap) return;
    if (image.planes.length != 1) return; // not NV21 (unexpected on Android)
    _lastFrame = now;
    _encoding = true;
    final frame = Nv21Frame(
      width: image.width,
      height: image.height,
      bytes: Uint8List.fromList(image.planes.first.bytes), // platform buffer is reused
      rotate180: rotate180,
    );
    compute(encodeNv21Frame, frame).then((jpeg) {
      if (!_closed) {
        link?.sendBinary(jpeg);
        _sentThisSecond++;
      }
    }).whenComplete(() => _encoding = false);
  }

  Future<void> close() async {
    _closed = true;
    _fpsTimer?.cancel();
    _imu?.stop();
    link?.dispose();
    link = null;
    final cam = controller;
    controller = null;
    if (cam != null) {
      if (cam.value.isStreamingImages) await cam.stopImageStream();
      await cam.dispose();
    }
    status.dispose();
    fps.dispose();
  }
}
