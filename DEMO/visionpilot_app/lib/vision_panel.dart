import 'dart:typed_data';

import 'package:flutter/material.dart';

import 'vision_state.dart';

const _modeNames = {
  'manual': 'Manual',
  'assist': 'Assist',
  'follow': 'Follow',
  'explore': 'Explore',
  'replay': 'Replay',
  'handheld': 'Hand-held',
};

/// Centre panel while VISION is on: what the AI sees + mode + target picking.
class VisionPanel extends StatelessWidget {
  final VisionState? state;
  final Uint8List? frame;
  final void Function(Map<String, Object?> command) send;

  /// Replaces the downloaded AI video (Controller + Camera shows its own preview).
  final Widget? video;

  const VisionPanel({super.key, required this.state, required this.frame, required this.send, this.video});

  @override
  Widget build(BuildContext context) {
    final s = state;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        ModeChips(state: s, send: send),
        const SizedBox(height: 4),
        Expanded(
          child: ClipRRect(
            borderRadius: BorderRadius.circular(10),
            child: video ?? _VideoView(frame: frame, send: send),
          ),
        ),
        const SizedBox(height: 6),
        _StatusLine(state: s),
        _TargetRow(state: s, send: send),
      ],
    );
  }
}

class ModeChips extends StatelessWidget {
  final VisionState? state;
  final void Function(Map<String, Object?>) send;
  const ModeChips({super.key, required this.state, required this.send});

  @override
  Widget build(BuildContext context) {
    final modes = state?.modes ?? const VisionState().modes;
    return Wrap(
      spacing: 6,
      runSpacing: 4,
      alignment: WrapAlignment.center,
      children: [
        for (final mode in modes)
          ChoiceChip(
            label: Text(_modeNames[mode] ?? mode, style: const TextStyle(fontSize: 12)),
            selected: state?.mode == mode,
            visualDensity: VisualDensity.compact,
            selectedColor: Colors.greenAccent.shade700,
            onSelected: (_) => send({'type': 'mode', 'mode': mode}),
          ),
      ],
    );
  }
}

class _VideoView extends StatelessWidget {
  final Uint8List? frame;
  final void Function(Map<String, Object?>) send;
  const _VideoView({required this.frame, required this.send});

  @override
  Widget build(BuildContext context) {
    final bytes = frame;
    if (bytes == null) {
      return Container(
        decoration: BoxDecoration(color: Colors.black, borderRadius: BorderRadius.circular(10)),
        alignment: Alignment.center,
        child: const Text(
          'Waiting for AI video...\nOpen the camera page on the car phone.',
          textAlign: TextAlign.center,
          style: TextStyle(color: Colors.white54, fontSize: 12),
        ),
      );
    }
    final imageSize = jpegSize(bytes) ?? const Size(640, 360);
    return ClipRRect(
      borderRadius: BorderRadius.circular(10),
      child: ColoredBox(
        color: Colors.black,
        child: LayoutBuilder(
          builder: (context, box) => GestureDetector(
            onTapUp: (tap) {
              final point = containTap(Size(box.maxWidth, box.maxHeight), imageSize, tap.localPosition);
              if (point != null) send({'type': 'tap', 'x': point.dx, 'y': point.dy});
            },
            child: SizedBox.expand(
              child: Image.memory(bytes, gaplessPlayback: true, fit: BoxFit.contain),
            ),
          ),
        ),
      ),
    );
  }
}

class _StatusLine extends StatelessWidget {
  final VisionState? state;
  const _StatusLine({required this.state});

  @override
  Widget build(BuildContext context) {
    final s = state;
    if (s == null) {
      return const Text('Connecting to laptop...', style: TextStyle(color: Colors.white54, fontSize: 12));
    }
    final safety = s.safety;
    return Text(
      safety != null && safety != 'standby' ? 'STOP: $safety | ${s.status}' : s.status,
      maxLines: 1,
      overflow: TextOverflow.ellipsis,
      style: TextStyle(color: safety != null ? Colors.orangeAccent : Colors.greenAccent, fontSize: 12),
    );
  }
}

class _TargetRow extends StatelessWidget {
  final VisionState? state;
  final void Function(Map<String, Object?>) send;
  const _TargetRow({required this.state, required this.send});

  @override
  Widget build(BuildContext context) {
    final labels = state?.labels ?? const <String>[];
    final current = labels.contains(state?.targetLabel) ? state?.targetLabel : null;
    return Row(
      children: [
        Expanded(
          child: DropdownButton<String>(
            isExpanded: true,
            isDense: true,
            value: current,
            hint: Text('tap video or pick: ${state?.targetText ?? 'no target'}',
                style: const TextStyle(fontSize: 12, color: Colors.white54)),
            items: [
              for (final label in labels)
                DropdownMenuItem(value: label, child: Text(label, style: const TextStyle(fontSize: 12))),
            ],
            onChanged: (label) => send({'type': 'target_class', 'label': label}),
          ),
        ),
        IconButton(
          tooltip: 'Clear target',
          visualDensity: VisualDensity.compact,
          icon: const Icon(Icons.clear, size: 18, color: Colors.white54),
          onPressed: () => send({'type': 'clear_target'}),
        ),
      ],
    );
  }
}
