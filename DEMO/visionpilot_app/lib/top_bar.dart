import 'package:flutter/material.dart';

/// One thin (40 px) header row: status dot, "VP" logo, role, info text, actions, settings.
class CompactTopBar extends StatelessWidget implements PreferredSizeWidget {
  static const height = 40.0;

  final Color stateColor;
  final String stateLabel;
  final IconData roleIcon;
  final String info;
  final List<Widget> actions;
  final VoidCallback? onOpenSettings;

  const CompactTopBar({
    super.key,
    required this.stateColor,
    required this.stateLabel,
    required this.roleIcon,
    required this.info,
    required this.actions,
    this.onOpenSettings,
  });

  @override
  Size get preferredSize => const Size.fromHeight(height);

  @override
  Widget build(BuildContext context) {
    return Material(
      key: const Key('top-bar'),
      color: const Color(0xFF16213E),
      child: SafeArea(
        bottom: false,
        child: SizedBox(
          height: height,
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 10),
            child: Row(children: [
              Container(
                width: 9,
                height: 9,
                decoration:
                    BoxDecoration(color: stateColor, shape: BoxShape.circle),
              ),
              const SizedBox(width: 6),
              Text(stateLabel,
                  style: TextStyle(
                      color: stateColor,
                      fontSize: 12,
                      fontWeight: FontWeight.bold)),
              const SizedBox(width: 10),
              const Text('VP',
                  style: TextStyle(
                      color: Colors.white,
                      fontSize: 13,
                      fontWeight: FontWeight.w900,
                      letterSpacing: 1)),
              const SizedBox(width: 6),
              Icon(roleIcon, size: 16, color: Colors.white54),
              const SizedBox(width: 10),
              Expanded(
                child: Text(info,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                        color: Colors.lightBlueAccent, fontSize: 11)),
              ),
              for (final action in actions) ...[
                const SizedBox(width: 6),
                action
              ],
              if (onOpenSettings != null)
                IconButton(
                  key: const Key('settings-button'),
                  tooltip: 'Settings',
                  visualDensity: VisualDensity.compact,
                  iconSize: 20,
                  icon: const Icon(Icons.settings, color: Colors.white70),
                  onPressed: onOpenSettings,
                ),
            ]),
          ),
        ),
      ),
    );
  }
}

/// Small dense button for the top bar (32 px high).
class BarButton extends StatelessWidget {
  final String label;
  final Color color;
  final VoidCallback onPressed;
  final Widget? icon;

  const BarButton(
      {super.key,
      required this.label,
      required this.color,
      required this.onPressed,
      this.icon});

  @override
  Widget build(BuildContext context) {
    final style = ElevatedButton.styleFrom(
      backgroundColor: color,
      minimumSize: const Size(0, 30),
      padding: const EdgeInsets.symmetric(horizontal: 10),
      tapTargetSize: MaterialTapTargetSize.shrinkWrap,
      visualDensity: VisualDensity.compact,
    );
    final text =
        Text(label, style: const TextStyle(color: Colors.white, fontSize: 12));
    final leading = icon;
    return SizedBox(
      height: 30,
      child: leading == null
          ? ElevatedButton(style: style, onPressed: onPressed, child: text)
          : ElevatedButton.icon(
              style: style, onPressed: onPressed, icon: leading, label: text),
    );
  }
}
