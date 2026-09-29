import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'app_role.dart';
import 'camera_screen.dart';
import 'car_socket.dart';
import 'control_screen.dart';
import 'settings_screen.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  // One fixed landscape so camera frames from the back sensor arrive upright.
  SystemChrome.setPreferredOrientations([DeviceOrientation.landscapeLeft]);
  runApp(const VisionPilotApp());
}

class VisionPilotApp extends StatelessWidget {
  const VisionPilotApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'VisionPilot',
      debugShowCheckedModeBanner: false,
      theme: ThemeData.dark(),
      home: const RoleShell(),
    );
  }
}

typedef CarSocketFactory = Future<CarSocket> Function(String carIp, int cmdPort);
typedef CameraScreenBuilder = Widget Function(VoidCallback openSettings);

Future<CarSocket> startCarSocket(String carIp, int cmdPort) async {
  final socket = CarSocket(carIp: carIp, cmdPort: cmdPort);
  await socket.start();
  return socket;
}

Widget buildCameraScreen(VoidCallback openSettings) => CameraScreen(onOpenSettings: openSettings);

/// Picks the screen for this phone's role. Only roles that drive the car start
/// the 20 Hz UDP drive loop - the Camera role must never send drive packets.
class RoleShell extends StatefulWidget {
  final CarSocketFactory carSocketFactory;
  final CameraScreenBuilder cameraScreenBuilder;

  const RoleShell({
    super.key,
    this.carSocketFactory = startCarSocket,
    this.cameraScreenBuilder = buildCameraScreen,
  });

  @override
  State<RoleShell> createState() => _RoleShellState();
}

class _RoleShellState extends State<RoleShell> {
  AppRole? _role;
  CarSocket? _socket;
  String _carIp = '192.168.4.1';

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _socket?.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    final prefs = await SharedPreferences.getInstance();
    final role = AppRole.parse(prefs.getString(AppRole.prefsKey));
    _carIp = prefs.getString('car_ip') ?? '192.168.4.1';
    final port = prefs.getInt('cmd_port') ?? 4210;
    if (role.drivesCar && _socket == null) {
      _socket = await widget.carSocketFactory(_carIp, port);
    } else if (!role.drivesCar && _socket != null) {
      _socket?.dispose(); // stop the drive loop before becoming a camera
      _socket = null;
    }
    if (mounted) setState(() => _role = role);
  }

  Future<void> _openSettings() async {
    await Navigator.push(context, MaterialPageRoute(builder: (_) => const SettingsScreen()));
    await _load(); // the role may have changed
  }

  @override
  Widget build(BuildContext context) {
    final role = _role;
    final socket = _socket;
    if (role == null || (role.drivesCar && socket == null)) {
      return const Scaffold(
        backgroundColor: Color(0xFF1A1A2E),
        body: Center(child: CircularProgressIndicator(color: Colors.greenAccent)),
      );
    }
    if (!role.drivesCar || socket == null) {
      return widget.cameraScreenBuilder(_openSettings);
    }
    return ControlScreen(
      key: ValueKey(role),
      socket: socket,
      carIp: _carIp,
      role: role,
      onOpenSettings: _openSettings,
    );
  }
}
