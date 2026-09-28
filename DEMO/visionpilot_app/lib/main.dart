import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'car_socket.dart';
import 'control_screen.dart';
import 'settings_screen.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  SystemChrome.setPreferredOrientations(
      [DeviceOrientation.landscapeLeft, DeviceOrientation.landscapeRight]);
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
      home: const _Loader(),
    );
  }
}

class _Loader extends StatefulWidget {
  const _Loader();

  @override
  State<_Loader> createState() => _LoaderState();
}

class _LoaderState extends State<_Loader> {
  @override
  void initState() {
    super.initState();
    _init();
  }

  Future<void> _init() async {
    final prefs = await SharedPreferences.getInstance();
    final ip = prefs.getString('car_ip') ?? '192.168.4.1';
    final port = prefs.getInt('cmd_port') ?? 4210;
    final socket = CarSocket(carIp: ip, cmdPort: port);
    await socket.start();
    if (mounted) {
      Navigator.of(context).pushReplacement(MaterialPageRoute(
        builder: (_) => _HomeShell(socket: socket, carIp: ip),
      ));
    }
  }

  @override
  Widget build(BuildContext context) {
    return const Scaffold(
      backgroundColor: Color(0xFF1A1A2E),
      body: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            CircularProgressIndicator(color: Colors.greenAccent),
            SizedBox(height: 16),
            Text('Connecting…', style: TextStyle(color: Colors.white70)),
          ],
        ),
      ),
    );
  }
}

class _HomeShell extends StatelessWidget {
  final CarSocket socket;
  final String carIp;
  const _HomeShell({required this.socket, required this.carIp});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: ControlScreen(socket: socket, carIp: carIp),
      floatingActionButton: FloatingActionButton.small(
        backgroundColor: const Color(0xFF16213E),
        child: const Icon(Icons.settings, color: Colors.white70),
        onPressed: () => Navigator.push(
            context, MaterialPageRoute(builder: (_) => const SettingsScreen())),
      ),
    );
  }
}
