import 'package:flutter/material.dart';
import 'car_socket.dart';
import 'joystick_widget.dart';

class ControlScreen extends StatefulWidget {
  final CarSocket socket;
  final String carIp;

  const ControlScreen({super.key, required this.socket, required this.carIp});

  @override
  State<ControlScreen> createState() => _ControlScreenState();
}

class _ControlScreenState extends State<ControlScreen> {
  Telemetry? _telem;
  int _throttle = 0;
  int _steer = 0;

  @override
  void initState() {
    super.initState();
    widget.socket.telemetry.listen((t) {
      if (mounted) setState(() => _telem = t);
    });
  }

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

  Color get _stateColor {
    switch (_telem?.state) {
      case CarState.ok: return Colors.greenAccent;
      case CarState.watchdog: return Colors.orange;
      case CarState.bumperLock: return Colors.yellow;
      case CarState.killed: return Colors.red;
      default: return Colors.grey;
    }
  }

  String get _stateLabel {
    switch (_telem?.state) {
      case CarState.ok: return 'OK';
      case CarState.watchdog: return 'WATCHDOG';
      case CarState.bumperLock: return 'BUMPER LOCK';
      case CarState.killed: return 'KILLED';
      default: return 'No signal';
    }
  }

  @override
  Widget build(BuildContext context) {
    final bumpers = _telem?.bumpers ?? [];
    final batV = _telem != null ? _telem!.batteryV.toStringAsFixed(1) : '--';

    return Scaffold(
      backgroundColor: const Color(0xFF1A1A2E),
      appBar: AppBar(
        backgroundColor: const Color(0xFF16213E),
        title: Row(children: [
          const Text('VisionPilot', style: TextStyle(color: Colors.white, fontSize: 16)),
          const Spacer(),
          ElevatedButton(
            style: ElevatedButton.styleFrom(backgroundColor: Colors.red.shade700),
            onPressed: widget.socket.sendKill,
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
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            color: const Color(0xFF0F3460),
            child: Row(children: [
              Container(width: 10, height: 10,
                  decoration: BoxDecoration(color: _stateColor, shape: BoxShape.circle)),
              const SizedBox(width: 8),
              Text(_stateLabel,
                  style: TextStyle(color: _stateColor, fontWeight: FontWeight.bold)),
              const SizedBox(width: 16),
              Text('Bat: ${batV}V', style: const TextStyle(color: Colors.white70)),
              const SizedBox(width: 16),
              Text('Bumpers: ${bumpers.isEmpty ? "none" : bumpers.join(" ")}',
                  style: TextStyle(color: bumpers.isEmpty ? Colors.white54 : Colors.yellow)),
              const Spacer(),
              Text('${widget.carIp}:4210',
                  style: const TextStyle(color: Colors.white30, fontSize: 11)),
            ]),
          ),
          Expanded(
            child: Padding(
              padding: const EdgeInsets.all(24),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                children: [
                  Expanded(
                    child: JoystickWidget(
                      label: 'SPEED  (↑ forward)',
                      verticalOnly: true,
                      onChanged: _onLeftStick,
                    ),
                  ),
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
            padding: const EdgeInsets.only(bottom: 16),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                _ValueChip(label: 'throttle', value: _throttle),
                const SizedBox(width: 24),
                _ValueChip(label: 'steer', value: _steer),
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
        : value < 0 ? Colors.redAccent : Colors.white38;
    return Column(children: [
      Text(label, style: const TextStyle(color: Colors.white38, fontSize: 11)),
      Text('${value > 0 ? "+" : ""}$value',
          style: TextStyle(color: color, fontSize: 22, fontWeight: FontWeight.bold)),
    ]);
  }
}
