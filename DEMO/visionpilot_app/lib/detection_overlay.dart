import 'dart:math' as math;

import 'package:camera/camera.dart';
import 'package:flutter/material.dart';

import 'vision_state.dart';

/// Draws what the laptop AI sees (boxes, focus, target, car marker) in
/// normalised coordinates over whatever is underneath (the local camera preview).
class DetectionPainter extends CustomPainter {
  final VisionState? state;
  DetectionPainter(this.state);

  @override
  void paint(Canvas canvas, Size size) {
    final s = state;
    if (s == null) return;
    const labelStyle = TextStyle(color: Colors.black, fontSize: 12, fontWeight: FontWeight.w600);
    for (final d in s.detections) {
      final focus = d.id != null && d.id == s.focus;
      final color = focus ? Colors.greenAccent : Colors.lightBlueAccent;
      final rect = Rect.fromLTRB(
        d.box[0] * size.width,
        d.box[1] * size.height,
        d.box[2] * size.width,
        d.box[3] * size.height,
      );
      canvas.drawRect(
        rect,
        Paint()
          ..color = color
          ..style = PaintingStyle.stroke
          ..strokeWidth = focus ? 4 : 2,
      );
      final tp = TextPainter(
        text: TextSpan(text: ' ${d.label} #${d.id ?? '-'} ', style: labelStyle),
        textDirection: TextDirection.ltr,
      )..layout();
      canvas.drawRect(
        Rect.fromLTWH(rect.left, rect.top - tp.height, tp.width, tp.height),
        Paint()..color = color,
      );
      tp.paint(canvas, Offset(rect.left, rect.top - tp.height));
    }
    final target = s.targetPoint;
    if (target != null) {
      canvas.drawCircle(
        Offset(target.dx * size.width, target.dy * size.height),
        16,
        Paint()
          ..color = Colors.pinkAccent
          ..style = PaintingStyle.stroke
          ..strokeWidth = 3,
      );
    }
    final marker = s.markerPosition;
    if (marker != null) {
      final c = Offset(marker.dx * size.width, marker.dy * size.height);
      final tip = c + Offset(math.cos(s.markerHeading), math.sin(s.markerHeading)) * 50;
      canvas.drawLine(
        c,
        tip,
        Paint()
          ..color = Colors.cyanAccent
          ..strokeWidth = 4,
      );
    }
  }

  @override
  bool shouldRepaint(DetectionPainter old) => old.state != state;
}

/// Local camera preview + AI overlay; taps become normalised target taps.
class LocalCameraView extends StatelessWidget {
  final CameraController? controller;
  final VisionState? state;
  final void Function(Offset normalised) onTap;
  final String placeholder;

  const LocalCameraView({
    super.key,
    required this.controller,
    required this.state,
    required this.onTap,
    this.placeholder = 'Starting camera...',
  });

  @override
  Widget build(BuildContext context) {
    final cam = controller;
    if (cam == null || !cam.value.isInitialized) {
      return Container(
        color: Colors.black,
        alignment: Alignment.center,
        child: Text(placeholder, style: const TextStyle(color: Colors.white54, fontSize: 12)),
      );
    }
    return ColoredBox(
      color: Colors.black,
      child: Center(
        child: AspectRatio(
          aspectRatio: cam.value.aspectRatio, // app is landscape-only
          child: LayoutBuilder(
            builder: (context, box) => GestureDetector(
              onTapUp: (tap) => onTap(Offset(
                (tap.localPosition.dx / box.maxWidth).clamp(0.0, 1.0),
                (tap.localPosition.dy / box.maxHeight).clamp(0.0, 1.0),
              )),
              child: Stack(
                fit: StackFit.expand,
                children: [
                  CameraPreview(cam),
                  CustomPaint(painter: DetectionPainter(state)),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
