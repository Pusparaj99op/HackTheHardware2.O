import 'dart:io';

import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'app_role.dart';
import 'camera_streamer.dart';
import 'laptop_link.dart';

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key});

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  final _ipCtrl = TextEditingController(text: '192.168.4.1');
  final _portCtrl = TextEditingController(text: '4210');
  final _laptopCtrl = TextEditingController();
  bool _searching = false;
  AppRole _role = AppRole.controller;
  bool _rotate180 = false;

  Future<void> _setRole(AppRole role) async {
    setState(() => _role = role);
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(AppRole.prefsKey, role.name);
  }

  Future<void> _setRotate(bool value) async {
    setState(() => _rotate180 = value);
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(CameraSession.rotateKey, value);
  }

  @override
  void dispose() {
    _ipCtrl.dispose();
    _portCtrl.dispose();
    _laptopCtrl.dispose();
    super.dispose();
  }

  Future<void> _findLaptop() async {
    setState(() => _searching = true);
    final found = await LaptopLink.discover();
    if (!mounted) return;
    setState(() => _searching = false);
    if (found == null) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          content: Text(
              'No laptop answered. Is it on the VisionPilot Wi-Fi with the server running?')));
      return;
    }
    _laptopCtrl.text = found.ip;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('laptop_ip', found.ip);
    await prefs.setInt('laptop_port', found.port);
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Laptop found at ${found.ip}:${found.port}')));
    }
  }

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final prefs = await SharedPreferences.getInstance();
    _ipCtrl.text = prefs.getString('car_ip') ?? '192.168.4.1';
    _portCtrl.text = (prefs.getInt('cmd_port') ?? 4210).toString();
    _laptopCtrl.text = prefs.getString('laptop_ip') ?? '';
    _role = AppRole.parse(prefs.getString(AppRole.prefsKey));
    _rotate180 = prefs.getBool(CameraSession.rotateKey) ?? false;
    if (mounted) setState(() {});
  }

  Future<void> _save() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('car_ip', _ipCtrl.text.trim());
    await prefs.setInt('cmd_port', int.tryParse(_portCtrl.text) ?? 4210);
    final laptop = _laptopCtrl.text.trim();
    if (laptop.isEmpty || InternetAddress.tryParse(laptop) == null) {
      await prefs.remove(
          'laptop_ip'); // empty/invalid -> auto-discover when VISION is pressed
    } else {
      await prefs.setString('laptop_ip', laptop);
    }
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Saved — restart app to apply')));
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF1A1A2E),
      appBar: AppBar(
        backgroundColor: const Color(0xFF16213E),
        title: const Text('Settings', style: TextStyle(color: Colors.white)),
        iconTheme: const IconThemeData(color: Colors.white),
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('This phone is the...',
                style: TextStyle(color: Colors.white70, fontSize: 13)),
            const SizedBox(height: 6),
            SegmentedButton<AppRole>(
              key: const Key('role-picker'),
              segments: [
                for (final role in AppRole.values)
                  ButtonSegment(
                      value: role,
                      label: Text(role.label),
                      icon: Icon(role.icon)),
              ],
              selected: {_role},
              onSelectionChanged: (selection) => _setRole(selection.first),
            ),
            const SizedBox(height: 4),
            const Text(
              'Controller: joysticks, AI video from the laptop.  Camera: this phone is the car\'s eyes '
              '(mount it on the car).  Controller + Camera: one phone does both.',
              style: TextStyle(color: Colors.white38, fontSize: 11),
            ),
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              dense: true,
              title: const Text('Rotate camera 180°',
                  style: TextStyle(color: Colors.white70, fontSize: 13)),
              subtitle: const Text('Use if the AI video is upside down',
                  style: TextStyle(color: Colors.white38, fontSize: 11)),
              value: _rotate180,
              onChanged: _setRotate,
            ),
            const SizedBox(height: 12),
            const Text('Car IP address',
                style: TextStyle(color: Colors.white70, fontSize: 13)),
            const SizedBox(height: 6),
            TextField(
              controller: _ipCtrl,
              style: const TextStyle(color: Colors.white),
              keyboardType: TextInputType.number,
              decoration: InputDecoration(
                hintText: '192.168.4.1',
                hintStyle: const TextStyle(color: Colors.white38),
                filled: true,
                fillColor: Colors.white10,
                border:
                    OutlineInputBorder(borderRadius: BorderRadius.circular(8)),
              ),
            ),
            const SizedBox(height: 16),
            const Text('Command port',
                style: TextStyle(color: Colors.white70, fontSize: 13)),
            const SizedBox(height: 6),
            TextField(
              controller: _portCtrl,
              style: const TextStyle(color: Colors.white),
              keyboardType: TextInputType.number,
              decoration: InputDecoration(
                hintText: '4210',
                hintStyle: const TextStyle(color: Colors.white38),
                filled: true,
                fillColor: Colors.white10,
                border:
                    OutlineInputBorder(borderRadius: BorderRadius.circular(8)),
              ),
            ),
            const SizedBox(height: 16),
            const Text('Laptop (vision brain) IP - empty = auto-discover',
                style: TextStyle(color: Colors.white70, fontSize: 13)),
            const SizedBox(height: 6),
            Row(children: [
              Expanded(
                child: TextField(
                  controller: _laptopCtrl,
                  style: const TextStyle(color: Colors.white),
                  keyboardType: TextInputType.number,
                  decoration: InputDecoration(
                    hintText: 'e.g. 192.168.4.2',
                    hintStyle: const TextStyle(color: Colors.white38),
                    filled: true,
                    fillColor: Colors.white10,
                    border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(8)),
                  ),
                ),
              ),
              const SizedBox(width: 12),
              ElevatedButton.icon(
                onPressed: _searching ? null : _findLaptop,
                icon: _searching
                    ? const SizedBox(
                        width: 16,
                        height: 16,
                        child: CircularProgressIndicator(strokeWidth: 2))
                    : const Icon(Icons.wifi_find),
                label: const Text('Find laptop'),
              ),
            ]),
            const SizedBox(height: 24),
            const Text(
              'ESP32 AP mode:\n'
              '  WiFi name: VisionPilot\n'
              '  Password:  vp123456\n'
              '  Car IP:    192.168.4.1',
              style:
                  TextStyle(color: Colors.white38, fontSize: 12, height: 1.7),
            ),
            const SizedBox(height: 24),
            SizedBox(
              width: double.infinity,
              child: ElevatedButton(
                style: ElevatedButton.styleFrom(
                    backgroundColor: Colors.greenAccent.shade700,
                    padding: const EdgeInsets.symmetric(vertical: 14)),
                onPressed: _save,
                child:
                    const Text('Save', style: TextStyle(color: Colors.black)),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
