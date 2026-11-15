import 'package:flutter/material.dart';

import '../theme/app_theme.dart';
import '../util/formatters.dart';

/// Icon + text pill. Status is never conveyed by color alone.
class InfoChip extends StatelessWidget {
  const InfoChip({
    super.key,
    required this.icon,
    required this.label,
    required this.background,
    required this.foreground,
  });
  final IconData icon;
  final String label;
  final Color background;
  final Color foreground;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
    decoration: BoxDecoration(
      color: background,
      borderRadius: BorderRadius.circular(AppRadius.sm),
    ),
    child: Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, size: 14, color: foreground),
        const SizedBox(width: 4),
        Text(
          label,
          style: TextStyle(
            color: foreground,
            fontSize: 12,
            fontWeight: FontWeight.w700,
          ),
        ),
      ],
    ),
  );
}

class StatusChip extends StatelessWidget {
  const StatusChip(this.status, {super.key});
  final String status;

  @override
  Widget build(BuildContext context) {
    final (icon, bg, fg) = switch (status) {
      'SUBMITTED' ||
      'TRIAGED' => (Icons.inbox, AppColors.canvas, AppColors.text),
      'SCHEDULED' => (
        Icons.event,
        AppColors.primaryTint,
        AppColors.primaryDark,
      ),
      'ACCEPTED' => (
        Icons.thumb_up_alt_outlined,
        AppColors.primaryTint,
        AppColors.primaryDark,
      ),
      'IN_PROGRESS' => (Icons.build, AppColors.primaryTint, AppColors.deep),
      'BLOCKED' => (
        Icons.pause_circle,
        AppColors.warningTint,
        AppColors.warningText,
      ),
      'COMPLETED' || 'CLOSED' => (
        Icons.check_circle,
        AppColors.primaryTint,
        AppColors.primaryDark,
      ),
      'REOPENED' => (
        Icons.replay,
        AppColors.warningTint,
        AppColors.warningText,
      ),
      'CANCELED' => (Icons.cancel, AppColors.dangerTint, AppColors.danger),
      _ => (Icons.help_outline, AppColors.canvas, AppColors.text),
    };
    return InfoChip(
      icon: icon,
      label: humanizeEnum(status),
      background: bg,
      foreground: fg,
    );
  }
}

class PriorityChip extends StatelessWidget {
  const PriorityChip(this.priority, {super.key});
  final String priority;

  @override
  Widget build(BuildContext context) {
    final (icon, bg, fg) = switch (priority) {
      'HIGH' => (Icons.priority_high, AppColors.dangerTint, AppColors.danger),
      'LOW' => (Icons.arrow_downward, AppColors.canvas, AppColors.text),
      _ => (Icons.remove, AppColors.canvas, AppColors.text),
    };
    return InfoChip(
      icon: icon,
      label: '${humanizeEnum(priority)} priority',
      background: bg,
      foreground: fg,
    );
  }
}

class SlaChip extends StatelessWidget {
  const SlaChip(this.state, {super.key});
  final String state;

  @override
  Widget build(BuildContext context) {
    final (icon, bg, fg) = switch (state) {
      'BREACHED' ||
      'OVERDUE' => (Icons.error, AppColors.dangerTint, AppColors.danger),
      'AT_RISK' => (
        Icons.warning_amber,
        AppColors.warningTint,
        AppColors.warningText,
      ),
      'PAUSED' => (Icons.pause, AppColors.canvas, AppColors.text),
      _ => (Icons.timer_outlined, AppColors.primaryTint, AppColors.primaryDark),
    };
    return InfoChip(
      icon: icon,
      label: 'SLA ${humanizeEnum(state).toLowerCase()}',
      background: bg,
      foreground: fg,
    );
  }
}
