import 'dart:async';
import 'dart:io';

import 'package:camera/camera.dart';
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:wakelock_plus/wakelock_plus.dart';

import 'app_role.dart';
import 'camera_streamer.dart';
import 'detection_overlay.dart';
import 'top_bar.dart';
import 'vision_panel.dart';
import 'vision_state.dart';

/// CAMERA role: this phone is the car's eyes. It never drives the car itself.
class CameraScreen extends StatefulWidget {
  final VoidCallback? onOpenSettings;

  const CameraScreen({super.key, this.onOpenSettings});

  @override
  State<CameraScreen> createState() => _CameraScreenState();
}

class _CameraScreenState extends State<CameraScreen>
    with WidgetsBindingObserver {
  final _session = CameraSession(
      deviceRotation: 0, useSavedLens: true); // portrait-locked role
  VisionState? _state;
  String? _error;
  bool _switching = false;
  StreamSubscription<VisionState>? _stateSub;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    WakelockPlus.enable();
    _session.status.addListener(_refresh);
    _session.fps.addListener(_refresh);
    _start();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    WakelockPlus.disable();
    _stateSub?.cancel();
    _session.status.removeListener(_refresh);
    _session.fps.removeListener(_refresh);
    _session.close();
    super.dispose();
  }

  void _refresh() {
    if (mounted) setState(() {});
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    // Android takes the camera away in the background; give it back cleanly.
    if (state == AppLifecycleState.inactive ||
        state == AppLifecycleState.paused) {
      _session.pause().then((_) => _refresh());
    } else if (state == AppLifecycleState.resumed) {
      _session
          .resume()
          .then((_) => _refresh())
          .catchError((Object e) => _showCameraError(e));
    }
  }

  Future<void> _start() async {
    setState(() => _error = null);
    try {
      await _session.start();
    } on CameraException catch (e) {
      _showCameraError(e);
      return;
    }
    _bindLink();
  }

  void _showCameraError(Object e) {
    if (!mounted) return;
    final message = switch (e) {
      CameraException(
        code: 'CameraAccessDenied' || 'CameraAccessDeniedWithoutPrompt'
      ) =>
        'Camera permission is off.\n'
            'Allow it in Android Settings > Apps > VisionPilot > Permissions.',
      CameraException(:final code, :final description) =>
        'Camera error: ${description ?? code}',
      _ => 'Camera error: $e',
    };
    setState(() => _error = message);
  }

  Future<void> _switchCamera() async {
    if (_switching) return;
    setState(() => _switching = true);
    try {
      await _session.switchCamera();
    } on CameraException catch (e) {
      _showCameraError(e);
    } finally {
      if (mounted) setState(() => _switching = false);
    }
  }

  void _bindLink() {
    _stateSub?.cancel();
    _stateSub = _session.link?.states.listen((s) {
      if (mounted) setState(() => _state = s);
    });
    _refresh();
  }

  Future<void> _retryLaptop() async {
    await _session.connectLaptop();
    _bindLink();
  }

  void _send(Map<String, Object?> command) => _session.link?.send(command);

  /// KILL goes to the laptop AND straight to the car (in case the laptop hangs).
  Future<void> _kill() async {
    _send({'type': 'kill'});
    final prefs = await SharedPreferences.getInstance();
    final carIp = prefs.getString('car_ip') ?? '192.168.4.1';
    final port = prefs.getInt('cmd_port') ?? 4210;
    try {
      final socket = await RawDatagramSocket.bind(InternetAddress.anyIPv4, 0);
      socket.send('K'.codeUnits, InternetAddress(carIp), port);
      socket.close();
    } on SocketException {
      // the laptop kill above still applies
    }
  }

  @override
  Widget build(BuildContext context) {
    final linked = _session.link?.connected.value ?? false;
    final s = _state;
    final safety = s?.safety;
    final info = [
      _session.status.value,
      '${_session.fps.value} fps',
      if (s != null) 'AI: ${s.visionStatus}',
    ].join(' | ');
    final error = _error;
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: CompactTopBar(
        stateColor: linked ? Colors.greenAccent : Colors.orange,
        stateLabel: linked ? 'LIVE' : 'NO LAPTOP',
        roleIcon: AppRole.camera.icon,
        info: info,
        onOpenSettings: widget.onOpenSettings,
        actions: [
          if (!linked)
            BarButton(
                label: 'RETRY',
                color: Colors.blueGrey,
                onPressed: _retryLaptop),
        ],
      ),
      body: error != null
          ? _ErrorView(message: error, onRetry: _start)
          : Column(children: [
              if (safety != null && safety != 'standby' && safety != 'ok')
                Container(
                  width: double.infinity,
                  color: Colors.red.shade900,
                  padding: const EdgeInsets.symmetric(vertical: 3),
                  child: Text('STOP: $safety',
                      textAlign: TextAlign.center,
                      style: const TextStyle(
                          color: Colors.white,
                          fontSize: 12,
                          fontWeight: FontWeight.bold)),
                ),
              Expanded(
                child: LocalCameraView(
                  controller: _session.controller,
                  state: s,
                  onTap: (p) => _send({'type': 'tap', 'x': p.dx, 'y': p.dy}),
                ),
              ),
              if (s != null)
                Padding(
                  padding: const EdgeInsets.only(top: 4),
                  child: Text(s.status,
                      style: const TextStyle(
                          color: Colors.greenAccent, fontSize: 12),
                      overflow: TextOverflow.ellipsis),
                ),
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 4, horizontal: 8),
                child: ModeChips(state: s, send: _send),
              ),
              SafeArea(
                top: false,
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(12, 0, 12, 10),
                  child: Row(children: [
                    IconButton.filledTonal(
                      key: const Key('switch-camera'),
                      tooltip: 'Switch camera',
                      iconSize: 28,
                      onPressed: _session.canSwitch && !_switching
                          ? _switchCamera
                          : null,
                      icon: _switching
                          ? const SizedBox(
                              width: 24,
                              height: 24,
                              child: CircularProgressIndicator(strokeWidth: 2))
                          : const Icon(Icons.cameraswitch),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: SizedBox(
                        height: 52,
                        child: FilledButton(
                          key: const Key('camera-kill'),
                          style: FilledButton.styleFrom(
                              backgroundColor: Colors.red.shade700,
                              foregroundColor: Colors.white),
                          onPressed: _kill,
                          child: const Text('KILL',
                              style: TextStyle(
                                  fontSize: 20,
                                  fontWeight: FontWeight.bold,
                                  letterSpacing: 2)),
                        ),
                      ),
                    ),
                  ]),
                ),
              ),
            ]),
    );
  }
}

class _ErrorView extends StatelessWidget {
  final String message;
  final VoidCallback onRetry;
  const _ErrorView({required this.message, required this.onRetry});

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          const Icon(Icons.no_photography, color: Colors.redAccent, size: 48),
          const SizedBox(height: 12),
          Text(message,
              textAlign: TextAlign.center,
              style: const TextStyle(color: Colors.white70)),
          const SizedBox(height: 16),
          FilledButton.icon(
              onPressed: onRetry,
              icon: const Icon(Icons.refresh),
              label: const Text('Try again')),
        ]),
      ),
    );
  }
}
