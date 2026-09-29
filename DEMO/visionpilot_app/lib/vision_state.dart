import 'dart:convert';
import 'dart:typed_data';
import 'dart:ui';

/// One object the laptop AI sees. Box coordinates are normalised 0..1.
class Detection {
  final int? id;
  final String label;
  final double conf;
  final List<double> box; // x1, y1, x2, y2

  const Detection({required this.id, required this.label, required this.conf, required this.box});

  static Detection? fromJson(Object? raw) {
    if (raw is! Map) return null;
    final box = raw['box'];
    if (box is! List || box.length != 4) return null;
    return Detection(
      id: raw['id'] is int ? raw['id'] as int : null,
      label: raw['label']?.toString() ?? '?',
      conf: _toDouble(raw['conf']),
      box: box.map(_toDouble).toList(growable: false),
    );
  }
}

/// The laptop brain's live state (the JSON "state" message on /ws/dash).
class VisionState {
  final String mode;
  final List<String> modes;
  final bool engaged;
  final String status;
  final String? safety;
  final bool carLinkOk;
  final String visionStatus;
  final List<Detection> detections;
  final List<String> labels;
  final String? targetLabel;
  final int? targetId;
  final int? focus;
  final bool cameraConnected;

  const VisionState({
    this.mode = 'manual',
    this.modes = const ['manual', 'assist', 'follow', 'explore', 'replay', 'handheld'],
    this.engaged = false,
    this.status = '',
    this.safety,
    this.carLinkOk = false,
    this.visionStatus = '',
    this.detections = const [],
    this.labels = const [],
    this.targetLabel,
    this.targetId,
    this.focus,
    this.cameraConnected = false,
  });

  factory VisionState.fromJson(Map<String, dynamic> j) {
    final target = j['target'] is Map ? j['target'] as Map : const {};
    final link = j['link'] is Map ? j['link'] as Map : const {};
    final vision = j['vision'] is Map ? j['vision'] as Map : const {};
    return VisionState(
      mode: j['mode']?.toString() ?? 'manual',
      modes: _strings(j['modes'], const VisionState().modes),
      engaged: j['engaged'] == true,
      status: j['status']?.toString() ?? '',
      safety: j['safety']?.toString(),
      carLinkOk: link['ok'] == true,
      visionStatus: vision['status']?.toString() ?? '',
      detections: (j['detections'] is List ? j['detections'] as List : const [])
          .map(Detection.fromJson)
          .whereType<Detection>()
          .toList(growable: false),
      labels: _strings(j['labels'], const []),
      targetLabel: target['label']?.toString(),
      targetId: target['track_id'] is int ? target['track_id'] as int : null,
      focus: j['focus'] is int ? j['focus'] as int : null,
      cameraConnected: j['phone_connected'] == true,
    );
  }

  /// Parses a WebSocket text message; null for anything that is not a state message.
  static VisionState? tryParse(String text) {
    try {
      final decoded = jsonDecode(text);
      if (decoded is Map<String, dynamic> && decoded['type'] == 'state') {
        return VisionState.fromJson(decoded);
      }
    } on FormatException {
      return null;
    }
    return null;
  }

  String get targetText {
    if (targetLabel == null && targetId == null) return 'no target';
    return '${targetLabel ?? 'object'}${targetId != null ? ' #$targetId' : ''}';
  }
}

/// Where the laptop reported an error (e.g. bad command) - shown as a snackbar.
String? tryParseError(String text) {
  try {
    final decoded = jsonDecode(text);
    if (decoded is Map && decoded['type'] == 'error') return decoded['message']?.toString();
  } on FormatException {
    return null;
  }
  return null;
}

/// Maps a tap inside a box showing an image with BoxFit.contain to normalised
/// image coordinates (0..1). Returns null when the tap is on the letterbox bars.
Offset? containTap(Size box, Size image, Offset tap) {
  if (image.width <= 0 || image.height <= 0) return null;
  final scale = (box.width / image.width) < (box.height / image.height)
      ? box.width / image.width
      : box.height / image.height;
  final w = image.width * scale;
  final h = image.height * scale;
  final x = (tap.dx - (box.width - w) / 2) / w;
  final y = (tap.dy - (box.height - h) / 2) / h;
  if (x < 0 || x > 1 || y < 0 || y > 1) return null;
  return Offset(x, y);
}

/// Width/height from a JPEG's SOF header without decoding the image.
Size? jpegSize(Uint8List bytes) {
  var i = 2;
  while (i + 9 < bytes.length) {
    if (bytes[i] != 0xFF) return null;
    final marker = bytes[i + 1];
    final length = (bytes[i + 2] << 8) | bytes[i + 3];
    if (marker >= 0xC0 && marker <= 0xC2) {
      final height = (bytes[i + 5] << 8) | bytes[i + 6];
      final width = (bytes[i + 7] << 8) | bytes[i + 8];
      return Size(width.toDouble(), height.toDouble());
    }
    i += 2 + length;
  }
  return null;
}

double _toDouble(Object? v) => v is num ? v.toDouble() : 0.0;

List<String> _strings(Object? raw, List<String> fallback) =>
    raw is List ? raw.map((e) => e.toString()).toList(growable: false) : fallback;
