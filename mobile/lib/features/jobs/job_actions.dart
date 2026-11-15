import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/providers.dart';
import '../../core/widgets/requires_connection.dart';

import '../../core/util/formatters.dart';
import '../../core/widgets/section_card.dart';
import 'job_models.dart';

const _actionLabels = <String, (IconData, String)>{
  'accept': (Icons.thumb_up_alt_outlined, 'Accept job'),
  'decline': (Icons.thumb_down_alt_outlined, 'Decline job'),
  'start': (Icons.play_arrow, 'Start work'),
  'resume': (Icons.play_circle_outline, 'Resume work'),
  'block': (Icons.pause_circle_outline, 'Report a blocker'),
  'complete': (Icons.check_circle_outline, 'Mark complete'),
  'add_note': (Icons.note_add_outlined, 'Add note'),
  'add_photo': (Icons.photo_camera_outlined, 'Add photo'),
  'log_materials': (Icons.inventory_2_outlined, 'Log materials'),
  'submit_estimate': (Icons.request_quote_outlined, 'Submit estimate'),
};

String actionLabel(String action) =>
    _actionLabels[action]?.$2 ?? humanizeEnum(action);

/// EXTENSION POINT (M3): replace the body of this widget with real controls
/// (status transitions, notes, evidence, materials) driven by [actions]
/// (`allowed_actions` from the server). M1 renders a read-only list.
class JobActionsSection extends ConsumerWidget {
  const JobActionsSection({
    super.key,
    required this.job,
    required this.actions,
  });
  final JobDetail job;
  final List<String> actions;

  /// Actions that work offline (queued in the outbox); everything else needs
  /// a connection (MOB-08) and is shown as unavailable while offline.
  static const offlineCapable = {'add_note', 'add_photo'};

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final offline = ref.watch(isOfflineProvider);
    return _build(context, offline);
  }

  Widget _build(BuildContext context, bool offline) => SectionCard(
    title: 'Available actions',
    children: [
      if (actions.isEmpty)
        const Text('No actions are available for this job right now.')
      else
        for (final a in actions)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 4),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Icon(_actionLabels[a]?.$1 ?? Icons.bolt, size: 18),
                    const SizedBox(width: 8),
                    Expanded(child: Text(actionLabel(a))),
                  ],
                ),
                if (offline && !offlineCapable.contains(a))
                  const RequiresConnectionLabel(),
              ],
            ),
          ),
    ],
  );
}
