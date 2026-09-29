import 'dart:math';
import 'package:flutter/material.dart';

class JoystickWidget extends StatefulWidget {
  final String label;
  final bool verticalOnly;
  final bool horizontalOnly;
  final void Function(double dx, double dy) onChanged;

  const JoystickWidget({
    super.key,
    required this.label,
    required this.onChanged,
    this.verticalOnly = false,
    this.horizontalOnly = false,
  });

  @override
  State<JoystickWidget> createState() => _JoystickWidgetState();
}

class _JoystickWidgetState extends State<JoystickWidget> {
  Offset _thumb = Offset.zero;

  void _update(Offset local, double radius) {
    var dx = (local.dx - radius) / radius;
    var dy = (local.dy - radius) / radius;
    final mag = sqrt(dx * dx + dy * dy);
    if (mag > 1.0) {
      dx /= mag;
      dy /= mag;
    }
    if (dx.abs() < 0.05) dx = 0;
    if (dy.abs() < 0.05) dy = 0;
    if (widget.verticalOnly) dx = 0;
    if (widget.horizontalOnly) dy = 0;
    setState(() => _thumb = Offset(dx, dy));
    widget.onChanged(dx, dy);
  }

  void _reset() {
    setState(() => _thumb = Offset.zero);
    widget.onChanged(0, 0);
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(widget.label,
            style: const TextStyle(color: Colors.white70, fontSize: 12)),
        const SizedBox(height: 6),
        LayoutBuilder(builder: (context, constraints) {
          final size = min(constraints.maxWidth, 160.0);
          final radius = size / 2;
          return GestureDetector(
            onPanStart: (d) => _update(d.localPosition, radius),
            onPanUpdate: (d) => _update(d.localPosition, radius),
            onPanEnd: (_) => _reset(),
            onPanCancel: _reset,
            child: CustomPaint(
              size: Size(size, size),
              painter: _JoystickPainter(_thumb),
            ),
          );
        }),
      ],
    );
  }
}

class _JoystickPainter extends CustomPainter {
  final Offset thumb;
  _JoystickPainter(this.thumb);

  @override
  void paint(Canvas canvas, Size size) {
    final r = size.width / 2;
    final center = Offset(r, r);
    canvas.drawCircle(
        center,
        r,
        Paint()
          ..color = Colors.white12
          ..style = PaintingStyle.fill);
    canvas.drawCircle(
        center,
        r,
        Paint()
          ..color = Colors.white30
          ..style = PaintingStyle.stroke
          ..strokeWidth = 2);
    final guide = Paint()
      ..color = Colors.white10
      ..strokeWidth = 1;
    canvas.drawLine(Offset(r, 0), Offset(r, size.height), guide);
    canvas.drawLine(Offset(0, r), Offset(size.width, r), guide);
    final thumbPos = center + Offset(thumb.dx * r * 0.8, thumb.dy * r * 0.8);
    canvas.drawCircle(thumbPos, r * 0.28,
        Paint()..color = Colors.greenAccent.withValues(alpha: 0.9));
  }

  @override
  bool shouldRepaint(_JoystickPainter old) => old.thumb != thumb;
}
