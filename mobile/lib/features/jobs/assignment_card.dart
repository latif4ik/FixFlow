import 'package:flutter/material.dart';

import '../../core/theme/app_theme.dart';
import '../../core/util/formatters.dart';
import '../../core/widgets/chips.dart';
import 'job_models.dart';

/// Inbox card. [timezone] is the organization's IANA zone.
class AssignmentCard extends StatelessWidget {
  const AssignmentCard({
    super.key,
    required this.item,
    required this.timezone,
    this.onTap,
  });
  final AssignmentItem item;
  final String timezone;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final a = item.appointment;
    return Card(
      child: InkWell(
        borderRadius: BorderRadius.circular(AppRadius.md),
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Text(
                    item.displayId,
                    style: const TextStyle(
                      fontWeight: FontWeight.w800,
                      color: AppColors.primaryDark,
                    ),
                  ),
                  const Spacer(),
                  StatusChip(item.status),
                ],
              ),
              const SizedBox(height: 6),
              Text(item.title, style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: 8),
              Wrap(
                spacing: 8,
                runSpacing: 6,
                children: [PriorityChip(item.priority)],
              ),
              const SizedBox(height: 10),
              _Line(
                Icons.schedule,
                a == null
                    ? 'No appointment'
                    : formatWindow(a.start, a.end, timezone),
              ),
              _Line(
                Icons.place_outlined,
                [
                  item.property.name,
                  item.property.address,
                ].where((e) => e.isNotEmpty).join(' · '),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _Line extends StatelessWidget {
  const _Line(this.icon, this.text);
  final IconData icon;
  final String text;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(top: 3),
    child: Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Icon(icon, size: 16, color: AppColors.muted),
        const SizedBox(width: 6),
        Expanded(child: Text(text)),
      ],
    ),
  );
}
