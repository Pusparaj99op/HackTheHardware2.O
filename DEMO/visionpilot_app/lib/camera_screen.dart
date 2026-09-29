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

class _CameraScreenState extends State<CameraScreen> {
  final _session = CameraSession();
  VisionState? _state;
  String? _error;
  StreamSubscription<VisionState>? _stateSub;

  @override
  void initState() {
    super.initState();
    WakelockPlus.enable();
    _session.status.addListener(_refresh);
    _session.fps.addListener(_refresh);
    _start();
  }

  @override
  void dispose() {
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

  Future<void> _start() async {
    try {
      await _session.start();
    } on CameraException catch (e) {
      if (mounted) setState(() => _error = 'Camera error: ${e.description ?? e.code}');
      return;
    }
    _bindLink();
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
    final info = [
      _session.status.value,
      '${_session.fps.value} fps',
      if (s != null) 'AI: ${s.visionStatus}',
      if (s?.safety != null && s?.safety != 'standby') 'STOP: ${s?.safety}',
    ].join(' | ');
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: CompactTopBar(
        stateColor: linked ? Colors.greenAccent : Colors.orange,
        stateLabel: linked ? 'LIVE' : 'NO LAPTOP',
        roleIcon: AppRole.camera.icon,
        info: info,
        onOpenSettings: widget.onOpenSettings,
        actions: [
          if (!linked) BarButton(label: 'RETRY', color: Colors.blueGrey, onPressed: _retryLaptop),
          BarButton(label: 'KILL', color: Colors.red.shade700, onPressed: _kill),
        ],
      ),
      body: _error != null
          ? Center(child: Text(_error!, style: const TextStyle(color: Colors.redAccent)))
          : Column(children: [
              Expanded(
                child: LocalCameraView(
                  controller: _session.controller,
                  state: s,
                  onTap: (p) => _send({'type': 'tap', 'x': p.dx, 'y': p.dy}),
                ),
              ),
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 4),
                child: ModeChips(state: s, send: _send),
              ),
              if (s != null)
                Padding(
                  padding: const EdgeInsets.only(bottom: 4),
                  child: Text(s.status,
                      style: const TextStyle(color: Colors.greenAccent, fontSize: 12),
                      overflow: TextOverflow.ellipsis),
                ),
            ]),
    );
  }
}
