import 'package:flutter/material.dart';

/// What this phone does. Saved in shared_preferences under [AppRole.prefsKey].
enum AppRole {
  /// Joysticks; the AI video comes from the laptop.
  controller('Controller', Icons.sports_esports),

  /// The car's eyes: streams camera + gyro to the laptop. Never drives the car.
  camera('Camera', Icons.videocam),

  /// One phone does both: joysticks + its own camera streamed while VISION is on.
  both('Controller + Camera', Icons.camera_front);

  const AppRole(this.label, this.icon);

  final String label;
  final IconData icon;

  static const prefsKey = 'role';

  static AppRole parse(String? name) =>
      AppRole.values.firstWhere((r) => r.name == name, orElse: () => AppRole.controller);

  /// Whether this role runs the 20 Hz UDP drive loop to the car.
  bool get drivesCar => this != AppRole.camera;

  /// Whether this role streams its own camera to the laptop.
  bool get streamsCamera => this != AppRole.controller;
}
