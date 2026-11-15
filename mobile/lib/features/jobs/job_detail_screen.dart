import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/providers.dart';
import '../../core/theme/app_theme.dart';
import '../../core/util/formatters.dart';
import '../../core/widgets/chips.dart';
import '../../core/widgets/section_card.dart';
import '../../core/widgets/stale_banner.dart';
import '../../core/widgets/state_views.dart';
import '../outbox/outbox_widgets.dart';
import 'job_actions.dart';
import 'job_materials.dart';
import 'job_models.dart';
import 'jobs_providers.dart';

class JobDetailScreen extends ConsumerWidget {
  const JobDetailScreen({super.key, required this.requestId, this.hint});
  final String requestId;

  /// Inbox item that opened this screen (carries contact instructions and
  /// `start_blocked_reason`, which /requests/{id} does not include).
  final AssignmentItem? hint;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final tz = ref.watch(
      sessionProvider.select((s) => s.selectedOrg?.timezone ?? 'UTC'),
    );
    final async = ref.watch(jobDetailProvider(requestId));
    return Scaffold(
      appBar: AppBar(title: Text(hint?.displayId ?? 'Job')),
      body: async.when(
        loading: () => const LoadingView(label: 'Loading job…'),
        error: (e, _) => ProblemView(
          error: e,
          notFoundMessage: 'You are no longer assigned to this job.',
          onRetry: () => ref.invalidate(jobDetailProvider(requestId)),
          extraActions: [
            TextButton(
              onPressed: () =>
                  context.canPop() ? context.pop() : context.go('/inbox'),
              child: const Text('Back to my jobs'),
            ),
          ],
        ),
        data: (job) => Column(
          children: [
            if (job.stale)
              StaleDataBanner(syncedAt: job.syncedAt, timezone: tz),
            Expanded(
              child: RefreshIndicator(
                onRefresh: () async {
                  ref.invalidate(jobDetailProvider(requestId));
                  await ref.read(jobDetailProvider(requestId).future);
                },
                child: JobDetailView(job: job, hint: hint, timezone: tz),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Pure presentation of a loaded job (widget-tested).
class JobDetailView extends StatelessWidget {
  const JobDetailView({
    super.key,
    required this.job,
    required this.timezone,
    this.hint,
  });
  final JobDetail job;
  final AssignmentItem? hint;
  final String timezone;

  @override
  Widget build(BuildContext context) {
    final p = job.property;
    final blocked = hint?.startBlockedReason;
    final contact = hint?.property.contactInstructions;
    final a = job.appointment;
    final e = job.estimate;
    final sla = job.sla;
    final gap = const SizedBox(height: 12);
    return ListView(
      physics: const AlwaysScrollableScrollPhysics(),
      padding: const EdgeInsets.all(16),
      children: [
        Text(job.title, style: Theme.of(context).textTheme.titleLarge),
        const SizedBox(height: 8),
        Wrap(
          spacing: 8,
          runSpacing: 6,
          children: [
            StatusChip(job.status),
            PriorityChip(job.priority),
            if (sla != null) SlaChip(sla.state),
          ],
        ),
        gap,
        if (blocked != null && blocked.isNotEmpty) ...[
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: AppColors.warningTint,
              borderRadius: BorderRadius.circular(AppRadius.sm),
            ),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Icon(
                  Icons.warning_amber,
                  color: AppColors.warningText,
                  size: 20,
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    'Cannot start yet: $blocked',
                    style: const TextStyle(color: AppColors.warningText),
                  ),
                ),
              ],
            ),
          ),
          gap,
        ],
        SectionCard(
          title: 'Where',
          children: [
            KeyValueRow('Property', p.name),
            KeyValueRow('Address', p.address),
            if (contact != null && contact.isNotEmpty)
              KeyValueRow('Contact', contact),
          ],
        ),
        gap,
        SectionCard(
          title: 'Job',
          children: [
            KeyValueRow('Category', job.categoryName),
            KeyValueRow('Priority', humanizeEnum(job.priority)),
            KeyValueRow(
              'Appointment',
              a == null
                  ? 'Not scheduled'
                  : formatWindow(a.start, a.end, timezone),
            ),
            if (job.asset != null) ...[
              KeyValueRow('Asset', '${job.asset!.code} · ${job.asset!.name}'),
              if (job.asset!.serial != null && job.asset!.serial!.isNotEmpty)
                KeyValueRow('Serial', job.asset!.serial!),
            ],
            if (job.requesterName != null)
              KeyValueRow('Requested by', job.requesterName!),
            if (sla != null) KeyValueRow('SLA', _slaText(sla, timezone)),
            KeyValueRow('Attachments', '${job.attachmentCount}'),
          ],
        ),
        gap,
        SectionCard(
          title: 'Description',
          children: [Text(job.description.isEmpty ? '-' : job.description)],
        ),
        if (e != null) ...[gap, _EstimateCard(e)],
        gap,
        JobMaterialsSection(job: job),
        JobActionsSection(
          job: job,
          actions: job.allowedActions,
          startBlockedReason: blocked,
        ),
        gap,
        JobNotesSection(
          requestId: job.id,
          notes: job.notes,
          timezone: timezone,
          canAddNote: job.allowedActions.contains('add_note'),
        ),
        gap,
        SectionCard(
          title: 'History',
          children: [
            if (job.timeline.isEmpty) const Text('No history.'),
            for (final t in job.timeline)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 4),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Icon(Icons.history, size: 16, color: AppColors.muted),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            t.toStatus != null
                                ? '${t.label}: ${humanizeEnum(t.toStatus!)}'
                                : t.label,
                            style: const TextStyle(fontWeight: FontWeight.w600),
                          ),
                          Text(
                            '${t.actorName ?? 'System'} · '
                            '${formatDateTime(t.createdAt, timezone)}',
                            style: const TextStyle(
                              fontSize: 12,
                              color: AppColors.muted,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
          ],
        ),
      ],
    );
  }
}

String _slaText(SlaInfo sla, String tz) {
  final state = humanizeEnum(sla.state);
  if (sla.paused) return '$state (paused)';
  if (sla.dueAt != null) return '$state, due ${formatDateTime(sla.dueAt!, tz)}';
  return state;
}

class _EstimateCard extends StatelessWidget {
  const _EstimateCard(this.e);
  final EstimateInfo e;

  @override
  Widget build(BuildContext context) => SectionCard(
    title: 'Estimate',
    trailing: InfoChip(
      icon: Icons.request_quote_outlined,
      label: humanizeEnum(e.status),
      background: AppColors.canvas,
      foreground: AppColors.text,
    ),
    children: [
      KeyValueRow(
        'Labor',
        '${formatMinutes(e.laborMinutes)} · ${formatMoney(e.laborCostMinor, e.currency)}',
      ),
      KeyValueRow('Materials', formatMoney(e.materialsTotalMinor, e.currency)),
      KeyValueRow('Total', formatMoney(e.totalMinor, e.currency)),
    ],
  );
}
