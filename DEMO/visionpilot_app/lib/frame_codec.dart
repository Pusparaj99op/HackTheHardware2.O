import 'dart:typed_data';

import 'package:image/image.dart' as img;

/// One camera frame to encode, sent to a background isolate via `compute()`.
class Nv21Frame {
  final int width;
  final int height;
  final Uint8List bytes; // NV21: Y plane (width*height) then interleaved V,U (width*height/2)
  final int targetWidth;
  final int quality;
  final bool rotate180;

  const Nv21Frame({
    required this.width,
    required this.height,
    required this.bytes,
    this.targetWidth = 640,
    this.quality = 60,
    this.rotate180 = false,
  });
}

/// NV21 camera frame -> small JPEG for the laptop (downscale + optional 180° turn in one pass).
///
/// Top-level so it can run in an isolate: `compute(encodeNv21Frame, frame)`.
Uint8List encodeNv21Frame(Nv21Frame f) {
  final w = f.width;
  final h = f.height;
  if (f.bytes.length < w * h * 3 ~/ 2) {
    throw ArgumentError('NV21 buffer too small: ${f.bytes.length} for ${w}x$h');
  }
  final outW = w < f.targetWidth ? w : f.targetWidth;
  final outH = (h * outW / w).round();
  final rgb = Uint8List(outW * outH * 3);
  final yuv = f.bytes;
  final uvStart = w * h;
  var o = 0;
  for (var oy = 0; oy < outH; oy++) {
    var sy = oy * h ~/ outH;
    if (f.rotate180) sy = h - 1 - sy;
    final yRow = sy * w;
    final uvRow = uvStart + (sy >> 1) * w;
    for (var ox = 0; ox < outW; ox++) {
      var sx = ox * w ~/ outW;
      if (f.rotate180) sx = w - 1 - sx;
      final y = yuv[yRow + sx];
      final uvIndex = uvRow + (sx & ~1);
      final v = yuv[uvIndex] - 128;
      final u = yuv[uvIndex + 1] - 128;
      rgb[o++] = _clamp(y + 1.402 * v);
      rgb[o++] = _clamp(y - 0.344 * u - 0.714 * v);
      rgb[o++] = _clamp(y + 1.772 * u);
    }
  }
  final image = img.Image.fromBytes(width: outW, height: outH, bytes: rgb.buffer, numChannels: 3);
  return img.encodeJpg(image, quality: f.quality);
}

int _clamp(double v) => v < 0 ? 0 : (v > 255 ? 255 : v.round());
