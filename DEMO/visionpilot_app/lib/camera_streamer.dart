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
  static const lensKey = 'camera_lens';

  /// How far the locked UI is turned clockwise from portrait (portraitUp 0, landscapeLeft 90).
  final int deviceRotation;

  /// Only the portrait Camera role offers the lens switch; the controller
  /// role always uses the back camera.
  final bool useSavedLens;

  CameraSession({this.deviceRotation = 90, this.useSavedLens = false});

  CameraController? controller;
  CameraLensDirection lens = CameraLensDirection.back;
  List<CameraDescription> _cameras = const [];
  LaptopLink? link;
  ImuStreamer? _imu;
  bool rotate180 = false;
  bool _encoding = false;
  DateTime _lastFrame = DateTime.fromMillisecondsSinceEpoch(0);
  bool _closed = false;

  /// Camera open/close steps run one at a time (lifecycle events, the switch
  /// button and start() can overlap, e.g. around the permission dialog).
  Future<void> _cameraOps = Future.value();

  Future<void> _serial(Future<void> Function() op) {
    final next = _cameraOps.then((_) => op());
    _cameraOps =
        next.catchError((Object _) {}); // a failed step must not block the next
    return next;
  }

  /// Short human-readable status for the UI.
  final status = ValueNotifier<String>('starting camera...');

  /// Frames actually sent in the last second (shown in the UI).
  final fps = ValueNotifier<int>(0);
  int _sentThisSecond = 0;
  Timer? _fpsTimer;

  Future<void> start() async {
    final prefs = await SharedPreferences.getInstance();
    rotate180 = prefs.getBool(rotateKey) ?? false;
    lens = useSavedLens && prefs.getString(lensKey) == 'front'
        ? CameraLensDirection.front
        : CameraLensDirection.back;
    _cameras = await availableCameras();
    if (_cameras.isEmpty) {
      throw CameraException('no-camera', 'This phone has no camera');
    }
    await _serial(_startCamera);
    _fpsTimer?.cancel();
    _fpsTimer = Timer.periodic(const Duration(seconds: 1), (_) {
      fps.value = _sentThisSecond;
      _sentThisSecond = 0;
    });
    if (_closed) return;
    await connectLaptop(prefs);
  }

  /// True when the phone has both a back and a front camera.
  bool get canSwitch =>
      _cameras.any((c) => c.lensDirection == CameraLensDirection.back) &&
      _cameras.any((c) => c.lensDirection == CameraLensDirection.front);

  CameraDescription get _description => _cameras
      .firstWhere((c) => c.lensDirection == lens, orElse: () => _cameras.first);

  Future<void> _startCamera() async {
    final description = _description;
    lens = description.lensDirection;
    final cam = CameraController(
      description,
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
  }

  Future<void> _stopCamera() async {
    final cam = controller;
    controller = null;
    if (cam == null) return;
    if (cam.value.isStreamingImages) await cam.stopImageStream();
    await cam.dispose();
  }

  /// Back <-> front. The choice is remembered for next time.
  Future<void> switchCamera() async {
    if (!canSwitch || !useSavedLens || _closed) return;
    await _serial(() async {
      lens = lens == CameraLensDirection.back
          ? CameraLensDirection.front
          : CameraLensDirection.back;
      await _stopCamera();
      await _startCamera();
    });
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(
        lensKey, lens == CameraLensDirection.front ? 'front' : 'back');
  }

  /// App went to the background: release the camera (Android takes it away anyway).
  Future<void> pause() => _serial(_stopCamera);

  /// Back in the foreground: reopen the same lens.
  Future<void> resume() async {
    await _serial(() async {
      if (_closed || controller != null || _cameras.isEmpty) return;
      await _startCamera();
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
    if (_closed || _encoding || current == null || !current.connected.value) {
      return;
    }
    if (now.difference(_lastFrame) < _minFrameGap) return;
    if (image.planes.length != 1) return; // not NV21 (unexpected on Android)
    final description = controller?.description;
    if (description == null) return;
    _lastFrame = now;
    _encoding = true;
    final front = description.lensDirection == CameraLensDirection.front;
    final upright = uprightRotation(
      sensorOrientation: description.sensorOrientation,
      deviceRotation: deviceRotation,
      front: front,
    );
    final frame = Nv21Frame(
      width: image.width,
      height: image.height,
      bytes: Uint8List.fromList(
          image.planes.first.bytes), // platform buffer is reused
      rotationDegrees: upright + (rotate180 ? 180 : 0),
      mirror:
          front, // selfie view, same as the preview, so boxes and taps line up
    );
    compute(encodeNv21Frame, frame).then((jpeg) {
      if (!_closed) {
        link?.sendBinary(jpeg);
        _sentThisSecond++;
      }
    }).catchError((Object e) {
      debugPrint('frame encode failed: $e'); // drop this frame, keep streaming
    }).whenComplete(() => _encoding = false);
  }

  Future<void> close() async {
    _closed = true;
    _fpsTimer?.cancel();
    _imu?.stop();
    link?.dispose();
    link = null;
    await _serial(_stopCamera);
    status.dispose();
    fps.dispose();
  }
}
