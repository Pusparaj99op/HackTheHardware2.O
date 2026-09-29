import 'dart:async';
import 'dart:io';

enum CarState { ok, watchdog, bumperLock, killed, disconnected }

class Telemetry {
  final int seq;
  final int bumperMask;
  final int batteryMv;
  final CarState state;
  Telemetry(this.seq, this.bumperMask, this.batteryMv, this.state);

  List<String> get bumpers {
    final names = <String>[];
    if (bumperMask & 1 != 0) names.add('L');
    if (bumperMask & 2 != 0) names.add('C');
    if (bumperMask & 4 != 0) names.add('R');
    return names;
  }

  double get batteryV => batteryMv / 1000.0;
}

class CarSocket {
  final String carIp;
  final int cmdPort;
  final int telemPort;

  RawDatagramSocket? _cmdSock;
  RawDatagramSocket? _telemSock;
  Timer? _driveTimer;
  int _seq = 0;
  int _throttle = 0;
  int _steer = 0;

  final _telemController = StreamController<Telemetry>.broadcast();
  Stream<Telemetry> get telemetry => _telemController.stream;

  CarSocket({this.carIp = '192.168.4.1', this.cmdPort = 4210, this.telemPort = 4211});

  Future<void> start() async {
    _cmdSock = await RawDatagramSocket.bind(InternetAddress.anyIPv4, 0);
    _telemSock = await RawDatagramSocket.bind(InternetAddress.anyIPv4, telemPort);
    _telemSock!.listen(_onDatagram);
    // 20 Hz drive loop — matches laptop control rate
    _driveTimer = Timer.periodic(const Duration(milliseconds: 50), (_) => _sendDrive());
  }

  void _onDatagram(RawSocketEvent event) {
    if (event != RawSocketEvent.read) return;
    final dg = _telemSock!.receive();
    if (dg == null) return;
    final msg = String.fromCharCodes(dg.data).trim();
    final parts = msg.split(',');
    if (parts.length != 5 || parts[0] != 'T') return;
    try {
      final seq = int.parse(parts[1]);
      final mask = int.parse(parts[2]);
      final mv = int.parse(parts[3]);
      final stateIdx = int.parse(parts[4]);
      final state = CarState.values[stateIdx.clamp(0, 3)];
      _telemController.add(Telemetry(seq, mask, mv, state));
    } catch (_) {}
  }

  void setDrive(int throttle, int steer) {
    _throttle = throttle.clamp(-100, 100);
    _steer = steer.clamp(-100, 100);
  }

  /// While VISION is on the laptop drives the car: we must not send drive
  /// packets (the car would jitter between two drivers), only a slow ping so
  /// the car keeps sending us telemetry.
  bool paused = false;
  int _tick = 0;

  void _sendDrive() {
    _tick++;
    final packet = packetFor(
      paused: paused,
      tick: _tick,
      seq: _seq + 1,
      throttle: _throttle,
      steer: _steer,
    );
    if (packet == null) return;
    if (packet.startsWith('D')) _seq = (_seq + 1) & 0xFFFFFFFF;
    _send(packet);
  }

  static const pingEveryTicks = 10; // 20 Hz loop -> 2 Hz ping

  /// Pure packet choice for one 20 Hz tick (unit-tested).
  static String? packetFor({
    required bool paused,
    required int tick,
    required int seq,
    required int throttle,
    required int steer,
  }) {
    if (!paused) return 'D,${seq & 0xFFFFFFFF},$throttle,$steer';
    return tick % pingEveryTicks == 0 ? 'P' : null;
  }

  void sendKill() => _send('K');
  void sendClear() => _send('C');

  void _send(String msg) {
    _cmdSock?.send(msg.codeUnits, InternetAddress(carIp), cmdPort);
  }

  void dispose() {
    _driveTimer?.cancel();
    _cmdSock?.close();
    _telemSock?.close();
    _telemController.close();
  }
}
