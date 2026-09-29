import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';

import 'vision_state.dart';

/// What the control screen needs from the laptop (faked in widget tests).
abstract interface class VisionLink {
  ValueListenable<bool> get connected;
  Stream<VisionState> get states;
  Stream<Uint8List> get frames;
  Stream<String> get errors;
  void send(Map<String, Object?> message);
  void dispose();
}

/// WebSocket link to the laptop vision brain (wss://<laptop>:8443/ws/dash).
///
/// Receives JSON state + annotated JPEG frames, sends commands. Reconnects
/// automatically; [connected] tells the UI whether the laptop is reachable.
class LaptopLink implements VisionLink {
  static const discoveryPort = 4212;
  static const _connectTimeout = Duration(seconds: 4);
  static const _retryDelay = Duration(seconds: 2);

  final String host;
  final int port;
  final bool tls;

  /// '/ws/dash' (controller: state + commands) or '/ws/phone' (camera: sends frames + gyro).
  final String path;

  /// false -> '?frames=0': don't download annotated video (we show our own camera).
  final bool withFrames;

  @override
  final ValueNotifier<bool> connected = ValueNotifier<bool>(false);
  final _states = StreamController<VisionState>.broadcast();
  final _frames = StreamController<Uint8List>.broadcast();
  final _errors = StreamController<String>.broadcast();

  WebSocket? _ws;
  Timer? _retry;
  bool _closed = false;

  LaptopLink({
    required this.host,
    this.port = 8443,
    this.tls = true,
    this.path = '/ws/dash',
    this.withFrames = true,
  });

  @override
  Stream<VisionState> get states => _states.stream;
  @override
  Stream<Uint8List> get frames => _frames.stream;
  @override
  Stream<String> get errors => _errors.stream;

  Uri get uri => Uri.parse(
      '${tls ? 'wss' : 'ws'}://$host:$port$path${withFrames ? '' : '?frames=0'}');

  /// Connects once; returns true when the socket is open.
  Future<bool> connect() async {
    if (_closed) return false;
    try {
      // The laptop uses a self-signed certificate: trust it for THIS host only.
      final client = HttpClient()
        ..badCertificateCallback =
            (cert, certHost, certPort) => certHost == host;
      final ws = await WebSocket.connect(uri.toString(), customClient: client)
          .timeout(_connectTimeout);
      _ws = ws;
      connected.value = true;
      ws.listen(_onMessage,
          onDone: _onClosed, onError: (_) => _onClosed(), cancelOnError: true);
      return true;
    } on Exception {
      // TimeoutException, SocketException, HandshakeException, WebSocketException
      _onClosed();
      return false;
    }
  }

  @override
  void send(Map<String, Object?> message) {
    final ws = _ws;
    if (ws != null && ws.readyState == WebSocket.open) {
      ws.add(jsonEncode(message));
    }
  }

  /// Sends a camera frame (JPEG) on the /ws/phone channel.
  void sendBinary(Uint8List data) {
    final ws = _ws;
    if (ws != null && ws.readyState == WebSocket.open) ws.add(data);
  }

  void _onMessage(dynamic data) {
    if (_closed) return; // late message after dispose(): controllers are closed
    if (data is String) {
      final state = VisionState.tryParse(data);
      if (state != null) {
        _states.add(state);
        return;
      }
      final error = tryParseError(data);
      if (error != null) _errors.add(error);
    } else if (data is List<int>) {
      _frames.add(data is Uint8List ? data : Uint8List.fromList(data));
    }
  }

  void _onClosed() {
    _ws = null;
    if (_closed) {
      return; // socket closed by dispose(): the notifier is already disposed
    }
    connected.value = false;
    _retry?.cancel();
    _retry = Timer(_retryDelay, connect);
  }

  @override
  void dispose() {
    _closed = true;
    _retry?.cancel();
    _ws?.close();
    connected.dispose();
    _states.close();
    _frames.close();
    _errors.close();
  }

  /// Finds and connects to the laptop: saved address first, then discovery.
  /// Returns null when no laptop answers.
  static Future<LaptopLink?> findAndConnect({
    String? savedIp,
    int savedPort = 8443,
    String path = '/ws/dash',
    bool frames = true,
  }) async {
    if (savedIp != null && savedIp.isNotEmpty) {
      final saved = LaptopLink(
          host: savedIp, port: savedPort, path: path, withFrames: frames);
      if (await saved.connect()) return saved;
      saved.dispose();
    }
    final found = await discover();
    if (found == null) return null;
    final link = LaptopLink(
      host: found.ip,
      port: found.port,
      tls: found.tls,
      path: path,
      withFrames: frames,
    );
    if (await link.connect()) return link;
    link.dispose();
    return null;
  }

  /// Broadcasts "VP?" on the car's Wi-Fi; the laptop answers "VPL,<port>,<tls>".
  /// Returns (ip, port, tls) or null after [timeout].
  static Future<({String ip, int port, bool tls})?> discover({
    Duration timeout = const Duration(seconds: 2),
  }) async {
    final socket = await RawDatagramSocket.bind(InternetAddress.anyIPv4, 0);
    socket.broadcastEnabled = true;
    final found = Completer<({String ip, int port, bool tls})?>();
    socket.listen((event) {
      if (event != RawSocketEvent.read) return;
      final dg = socket.receive();
      if (dg == null || found.isCompleted) return;
      final parts = ascii.decode(dg.data, allowInvalid: true).trim().split(',');
      if (parts.length == 3 && parts[0] == 'VPL') {
        found.complete((
          ip: dg.address.address,
          port: int.tryParse(parts[1]) ?? 8443,
          tls: parts[2] == '1'
        ));
      }
    });
    final request = ascii.encode('VP?');
    for (final target in ['192.168.4.255', '255.255.255.255']) {
      socket.send(request, InternetAddress(target), discoveryPort);
    }
    final result = await found.future.timeout(timeout, onTimeout: () => null);
    socket.close();
    return result;
  }
}
