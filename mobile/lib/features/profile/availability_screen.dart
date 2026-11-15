import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/providers.dart';
import '../../core/theme/app_theme.dart';
import '../../core/util/formatters.dart';
import '../../core/widgets/section_card.dart';
import '../../core/widgets/state_views.dart';
import 'availability.dart';

const weekdayNames = [
  'Monday',
  'Tuesday',
  'Wednesday',
  'Thursday',
  'Friday',
  'Saturday',
  'Sunday',
];

/// Read-only skills, weekly availability and upcoming time off (MOB-01).
class AvailabilityScreen extends ConsumerWidget {
  const AvailabilityScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final tz = ref.watch(
      sessionProvider.select((s) => s.selectedOrg?.timezone ?? 'UTC'),
    );
    final async = ref.watch(technicianProfileProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('My availability')),
      body: async.when(
        loading: () => const LoadingView(label: 'Loading availability…'),
        error: (e, _) => ProblemView(
          error: e,
          onRetry: () => ref.invalidate(technicianProfileProvider),
        ),
        data: (p) => RefreshIndicator(
          onRefresh: () async {
            ref.invalidate(technicianProfileProvider);
            await ref.read(technicianProfileProvider.future);
          },
          child: AvailabilityView(profile: p, timezone: tz),
        ),
      ),
    );
  }
}

class AvailabilityView extends StatelessWidget {
  const AvailabilityView({
    super.key,
    required this.profile,
    required this.timezone,
  });
  final TechnicianProfile profile;
  final String timezone;

  @override
  Widget build(BuildContext context) {
    final now = DateTime.now().toUtc();
    final upcoming = [
      for (final t in profile.timeOff)
        if (t.end.isAfter(now)) t,
    ]..sort((a, b) => a.start.compareTo(b.start));
    return ListView(
      physics: const AlwaysScrollableScrollPhysics(),
      padding: const EdgeInsets.all(16),
      children: [
        SectionCard(
          title: 'Skills',
          children: [
            if (profile.skills.isEmpty)
              const Text('No skills recorded.')
            else
              Wrap(
                spacing: 8,
                runSpacing: 6,
                children: [
                  for (final s in profile.skills)
                    Chip(label: Text(humanizeEnum(s))),
                ],
              ),
          ],
        ),
        const SizedBox(height: 12),
        SectionCard(
          title: 'Weekly availability',
          children: [
            Text(
              'Times are in the organization timezone ($timezone).',
              style: const TextStyle(fontSize: 12, color: AppColors.muted),
            ),
            const SizedBox(height: 8),
            for (var d = 0; d < 7; d++)
              KeyValueRow(weekdayNames[d], _dayText(d)),
          ],
        ),
        const SizedBox(height: 12),
        SectionCard(
          title: 'Upcoming time off',
          children: [
            if (upcoming.isEmpty) const Text('No upcoming time off.'),
            for (final t in upcoming)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 4),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Icon(Icons.beach_access_outlined, size: 18),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        '${formatDateTime(t.start, timezone)} – '
                        '${formatDateTime(t.end, timezone)}'
                        '${t.reason == null || t.reason!.isEmpty ? '' : '\n${t.reason}'}',
                      ),
                    ),
                  ],
                ),
              ),
          ],
        ),
        const SizedBox(height: 12),
        const Text(
          'Availability is managed by your dispatcher and is read-only here.',
          style: TextStyle(fontSize: 12, color: AppColors.muted),
        ),
      ],
    );
  }

  String _dayText(int weekday) {
    final slots = [
      for (final s in profile.availability)
        if (s.weekday == weekday) '${s.start}–${s.end}',
    ];
    return slots.isEmpty ? 'Not available' : slots.join(', ');
  }
}
