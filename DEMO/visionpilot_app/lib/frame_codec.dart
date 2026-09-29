import 'dart:typed_data';

import 'package:image/image.dart' as img;

/// One camera frame to encode, sent to a background isolate via `compute()`.
class Nv21Frame {
  final int width;
  final int height;
  final Uint8List
      bytes; // NV21: Y plane (width*height) then interleaved V,U (width*height/2)

  /// Longest side of the output JPEG (smaller frames are never upscaled).
  final int maxSide;
  final int quality;

  /// Clockwise turn applied to the sensor image: 0, 90, 180 or 270.
  final int rotationDegrees;

  /// Flip left/right after rotating (front camera, so it looks like a mirror).
  final bool mirror;

  const Nv21Frame({
    required this.width,
    required this.height,
    required this.bytes,
    this.maxSide = 640,
    this.quality = 60,
    this.rotationDegrees = 0,
    this.mirror = false,
  });
}

/// NV21 camera frame -> small upright JPEG for the laptop.
///
/// Downscale, rotation and mirroring happen in one pass: every output pixel
/// is mapped back to its source pixel. Top-level so it can run in an isolate:
/// `compute(encodeNv21Frame, frame)`.
Uint8List encodeNv21Frame(Nv21Frame f) {
  final w = f.width;
  final h = f.height;
  if (f.bytes.length < w * h * 3 ~/ 2) {
    throw ArgumentError('NV21 buffer too small: ${f.bytes.length} for ${w}x$h');
  }
  final rotation = f.rotationDegrees % 360;
  if (rotation % 90 != 0) {
    throw ArgumentError('rotation must be a multiple of 90: $rotation');
  }
  final sideways = rotation == 90 || rotation == 270;
  final rotW = sideways ? h : w;
  final rotH = sideways ? w : h;
  final longSide = rotW > rotH ? rotW : rotH;
  final scale = longSide > f.maxSide ? f.maxSide / longSide : 1.0;
  final outW = (rotW * scale).round();
  final outH = (rotH * scale).round();

  final rgb = Uint8List(outW * outH * 3);
  final yuv = f.bytes;
  final uvStart = w * h;
  var o = 0;
  for (var oy = 0; oy < outH; oy++) {
    final ry = oy * rotH ~/ outH; // row in the rotated (upright) image
    for (var ox = 0; ox < outW; ox++) {
      var rx = ox * rotW ~/ outW;
      if (f.mirror) rx = rotW - 1 - rx;
      // Upright (rx, ry) -> sensor (sx, sy) for a clockwise turn.
      final int sx;
      final int sy;
      switch (rotation) {
        case 90:
          sx = ry;
          sy = h - 1 - rx;
        case 180:
          sx = w - 1 - rx;
          sy = h - 1 - ry;
        case 270:
          sx = w - 1 - ry;
          sy = rx;
        default:
          sx = rx;
          sy = ry;
      }
      final y = yuv[sy * w + sx];
      final uvIndex = uvStart + (sy >> 1) * w + (sx & ~1);
      final v = yuv[uvIndex] - 128;
      final u = yuv[uvIndex + 1] - 128;
      rgb[o++] = _clamp(y + 1.402 * v);
      rgb[o++] = _clamp(y - 0.344 * u - 0.714 * v);
      rgb[o++] = _clamp(y + 1.772 * u);
    }
  }
  final image = img.Image.fromBytes(
      width: outW, height: outH, bytes: rgb.buffer, numChannels: 3);
  return img.encodeJpg(image, quality: f.quality);
}

/// Clockwise turn that makes the sensor image match the on-screen preview.
///
/// [deviceRotation] is how far the UI is turned clockwise from portrait
/// (portraitUp 0, landscapeLeft 90). Measured on a Galaxy S24: the front
/// stream needs an extra half turn to come out
/// upright; mirror it to match the selfie preview.
int uprightRotation(
    {required int sensorOrientation,
    required int deviceRotation,
    required bool front}) {
  final r = front
      ? sensorOrientation + deviceRotation + 180
      : sensorOrientation - deviceRotation;
  return ((r % 360) + 360) % 360;
}

int _clamp(double v) => v < 0 ? 0 : (v > 255 ? 255 : v.round());
