import 'dart:async';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'car_socket.dart';
import 'joystick_widget.dart';
import 'laptop_link.dart';
import 'vision_panel.dart';
import 'vision_state.dart';

/// Finds and connects to the laptop vision brain; null if not reachable.
typedef VisionConnector = Future<VisionLink?> Function();

Future<VisionLink?> connectSavedOrDiscoveredLaptop() async {
  final prefs = await SharedPreferences.getInstance();
  final link = await LaptopLink.findAndConnect(
    savedIp: prefs.getString('laptop_ip'),
    savedPort: prefs.getInt('laptop_port') ?? 8443,
  );
  if (link != null) {
    await prefs.setString('laptop_ip', link.host);
    await prefs.setInt('laptop_port', link.port);
  }
  return link;
}

class ControlScreen extends StatefulWidget {
  final CarSocket socket;
  final String carIp;
  final VisionConnector connectVision;

  const ControlScreen({
    super.key,
    required this.socket,
    required this.carIp,
    this.connectVision = connectSavedOrDiscoveredLaptop,
  });

  @override
  State<ControlScreen> createState() => _ControlScreenState();
}

class _ControlScreenState extends State<ControlScreen> {
  static const _overridePeriod = Duration(milliseconds: 50); // 20 Hz like the car loop

  Telemetry? _telem;
  int _throttle = 0;
  int _steer = 0;

  // ---- vision mode ----
  bool _vision = false;
  bool _connecting = false;
  VisionLink? _link;
  VisionState? _visionState;
  Uint8List? _frame;
  final _visionSubs = <StreamSubscription<Object?>>[];
  Timer? _overrideTimer;
  StreamSubscription<Telemetry>? _telemSub;

  @override
  void initState() {
    super.initState();
    _telemSub = widget.socket.telemetry.listen((t) {
      if (mounted) setState(() => _telem = t);
    });
  }

  @override
  void dispose() {
    _telemSub?.cancel();
    _teardownVision();
    super.dispose();
  }

  // ---------------------------------------------------------------- joysticks
  void _onLeftStick(double dx, double dy) {
    _throttle = (-dy * 100).round().clamp(-100, 100);
    widget.socket.setDrive(_throttle, _steer);
    setState(() {});
  }

  void _onRightStick(double dx, double dy) {
    _steer = (dx * 100).round().clamp(-100, 100);
    widget.socket.setDrive(_throttle, _steer);
    setState(() {});
  }

  /// While vision drives, any stick input is sent to the laptop as an override.
  void _sendOverride(Timer _) {
    if (_throttle == 0 && _steer == 0) return; // released: laptop resumes vision after 1 s
    _link?.send({'type': 'manual', 'throttle': _throttle, 'steer': _steer});
  }

  // ---------------------------------------------------------------- vision on/off
  Future<void> _toggleVision() async {
    if (_connecting) return;
    if (_vision) {
      _stopVision(sendRelease: true);
      return;
    }
    setState(() => _connecting = true);
    final link = await widget.connectVision();
    if (!mounted) {
      link?.dispose();
      return;
    }
    setState(() => _connecting = false);
    if (link == null) {
      _snack('Laptop not found. Join the laptop to the VisionPilot Wi-Fi, start the server, '
          'or set its IP in Settings.');
      return;
    }
    _startVision(link);
  }

  void _startVision(VisionLink link) {
    _link = link;
    _visionSubs
      ..add(link.states.listen((s) => setState(() => _visionState = s)))
      ..add(link.frames.listen((f) => setState(() => _frame = f)))
      ..add(link.errors.listen(_snack));
    link.connected.addListener(_onLinkChanged);
    widget.socket.paused = true; // hand the car over: the app stops sending drive packets
    link.send({'type': 'engage'});
    _overrideTimer = Timer.periodic(_overridePeriod, _sendOverride);
    setState(() => _vision = true);
  }

  void _onLinkChanged() {
    final link = _link;
    if (link != null && !link.connected.value && _vision) {
      _stopVision(sendRelease: false, reason: 'Laptop lost - back to direct joystick control');
    }
  }

  void _stopVision({required bool sendRelease, String? reason}) {
    if (sendRelease) _link?.send({'type': 'release'});
    _teardownVision();
    widget.socket.paused = false; // the app drives the car again
    if (mounted) setState(() => _vision = false);
    if (reason != null) _snack(reason);
  }

  void _teardownVision() {
    _overrideTimer?.cancel();
    _overrideTimer = null;
    for (final sub in _visionSubs) {
      sub.cancel();
    }
    _visionSubs.clear();
    _link?.connected.removeListener(_onLinkChanged);
    _link?.dispose();
    _link = null;
    _visionState = null;
    _frame = null;
  }

  void _kill() {
    widget.socket.sendKill(); // always straight to the car, even if the laptop hangs
    if (_vision) {
      _link?.send({'type': 'kill'});
      _stopVision(sendRelease: false);
    }
  }

  void _snack(String message) {
    if (!mounted) return;
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(content: Text(message)));
  }

  // ---------------------------------------------------------------- UI
  Color get _stateColor {
    switch (_telem?.state) {
      case CarState.ok:
        return Colors.greenAccent;
      case CarState.watchdog:
        return Colors.orange;
      case CarState.bumperLock:
        return Colors.yellow;
      case CarState.killed:
        return Colors.red;
      default:
        return Colors.grey;
    }
  }

  String get _stateLabel {
    switch (_telem?.state) {
      case CarState.ok:
        return 'OK';
      case CarState.watchdog:
        return 'WATCHDOG';
      case CarState.bumperLock:
        return 'BUMPER LOCK';
      case CarState.killed:
        return 'KILLED';
      default:
        return 'No signal';
    }
  }

  Widget _visionButton() {
    final on = _vision;
    return ElevatedButton.icon(
      key: const Key('vision-toggle'),
      style: ElevatedButton.styleFrom(
        backgroundColor: on ? Colors.greenAccent.shade700 : const Color(0xFF0F3460),
      ),
      onPressed: _toggleVision,
      icon: _connecting
          ? const SizedBox(
              width: 16,
              height: 16,
              child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
            )
          : Icon(on ? Icons.visibility : Icons.visibility_outlined, color: Colors.white),
      label: Text(on ? 'VISION ON' : 'VISION', style: const TextStyle(color: Colors.white)),
    );
  }

  Widget _statusBar() {
    final bumpers = _telem?.bumpers ?? [];
    final vs = _visionState;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      color: const Color(0xFF0F3460),
      child: Row(children: [
        Container(
          width: 10,
          height: 10,
          decoration: BoxDecoration(color: _stateColor, shape: BoxShape.circle),
        ),
        const SizedBox(width: 8),
        Text(_stateLabel, style: TextStyle(color: _stateColor, fontWeight: FontWeight.bold)),
        const SizedBox(width: 16),
        Text(
          'Bumpers: ${bumpers.isEmpty ? "none" : bumpers.join(" ")}',
          style: TextStyle(color: bumpers.isEmpty ? Colors.white54 : Colors.yellow),
        ),
        const SizedBox(width: 16),
        if (_vision)
          Expanded(
            child: Text(
              'AI: ${vs?.visionStatus ?? "connecting"}'
              '${vs != null && !vs.cameraConnected ? " | camera phone not connected" : ""}',
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(color: Colors.lightBlueAccent, fontSize: 12),
            ),
          )
        else
          const Spacer(),
        Text('${widget.carIp}:4210', style: const TextStyle(color: Colors.white30, fontSize: 11)),
      ]),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF1A1A2E),
      appBar: AppBar(
        backgroundColor: const Color(0xFF16213E),
        title: Row(children: [
          const Text('VisionPilot', style: TextStyle(color: Colors.white, fontSize: 16)),
          const Spacer(),
          _visionButton(),
          const SizedBox(width: 8),
          ElevatedButton(
            style: ElevatedButton.styleFrom(backgroundColor: Colors.red.shade700),
            onPressed: _kill,
            child: const Text('KILL', style: TextStyle(color: Colors.white)),
          ),
          const SizedBox(width: 8),
          ElevatedButton(
            style: ElevatedButton.styleFrom(backgroundColor: Colors.blueGrey),
            onPressed: widget.socket.sendClear,
            child: const Text('CLEAR', style: TextStyle(color: Colors.white)),
          ),
        ]),
      ),
      body: Column(
        children: [
          _statusBar(),
          Expanded(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(16, 12, 16, 8),
              child: Row(
                children: [
                  Expanded(
                    child: JoystickWidget(
                      label: 'SPEED  (↑ forward)',
                      verticalOnly: true,
                      onChanged: _onLeftStick,
                    ),
                  ),
                  if (_vision)
                    Expanded(
                      flex: 2,
                      child: VisionPanel(
                        state: _visionState,
                        frame: _frame,
                        send: (command) => _link?.send(command),
                      ),
                    )
                  else
                    const SizedBox(width: 32),
                  Expanded(
                    child: JoystickWidget(
                      label: 'STEERING  (← →)',
                      horizontalOnly: true,
                      onChanged: _onRightStick,
                    ),
                  ),
                ],
              ),
            ),
          ),
          Padding(
            padding: const EdgeInsets.only(bottom: 12),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                _ValueChip(label: 'throttle', value: _throttle),
                const SizedBox(width: 24),
                _ValueChip(label: 'steer', value: _steer),
                if (_vision) ...[
                  const SizedBox(width: 24),
                  const Text('touch a stick = manual override',
                      style: TextStyle(color: Colors.white38, fontSize: 11)),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _ValueChip extends StatelessWidget {
  final String label;
  final int value;
  const _ValueChip({required this.label, required this.value});

  @override
  Widget build(BuildContext context) {
    final color = value > 0
        ? Colors.greenAccent
        : value < 0
            ? Colors.redAccent
            : Colors.white38;
    return Column(children: [
      Text(label, style: const TextStyle(color: Colors.white38, fontSize: 11)),
      Text('${value > 0 ? "+" : ""}$value',
          style: TextStyle(color: color, fontSize: 22, fontWeight: FontWeight.bold)),
    ]);
  }
}
