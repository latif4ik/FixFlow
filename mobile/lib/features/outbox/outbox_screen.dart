import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/providers.dart';
import '../../core/theme/app_theme.dart';
import '../../core/widgets/state_views.dart';
import 'outbox_models.dart';
import 'outbox_providers.dart';
import 'outbox_widgets.dart';

/// All queued / conflicting notes of the current user in the current org.
class OutboxScreen extends ConsumerWidget {
  const OutboxScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final tz = ref.watch(
      sessionProvider.select((s) => s.selectedOrg?.timezone ?? 'UTC'),
    );
    final items = ref.watch(outboxItemsProvider).asData?.value ?? const [];
    final others = ref.watch(otherUsersOutboxCountProvider).asData?.value ?? 0;
    final conflicts = items.where((i) => i.isConflict).length;
    final pending = items.length - conflicts;
    return Scaffold(
      appBar: AppBar(title: const Text('Outbox')),
      body: items.isEmpty && others == 0
          ? const EmptyView(
              title: 'Nothing waiting',
              message: 'Notes written offline wait here until they are sent.',
            )
          : ListView(
              padding: const EdgeInsets.all(16),
              children: [
                Text(
                  '$pending waiting to sync · $conflicts need attention',
                  style: const TextStyle(fontWeight: FontWeight.w600),
                ),
                const SizedBox(height: 12),
                for (final i in items)
                  OutboxItemCard(item: i, timezone: tz, showJob: true),
                if (others > 0) ...[
                  const SizedBox(height: 8),
                  Container(
                    padding: const EdgeInsets.all(12),
                    decoration: BoxDecoration(
                      color: AppColors.warningTint,
                      borderRadius: BorderRadius.circular(AppRadius.md),
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          '$others queued item${others == 1 ? '' : 's'} belong to another account on this device. '
                          'They are never sent from your account.',
                          style: const TextStyle(color: AppColors.warningText),
                        ),
                        const SizedBox(height: 8),
                        OutlinedButton.icon(
                          onPressed: () => _discardOthers(context, ref, others),
                          icon: const Icon(Icons.delete_outline, size: 18),
                          label: const Text("Discard other account's items"),
                        ),
                      ],
                    ),
                  ),
                ],
              ],
            ),
    );
  }

  Future<void> _discardOthers(
    BuildContext context,
    WidgetRef ref,
    int count,
  ) async {
    final user = ref.read(currentUserIdProvider);
    if (user == null) return;
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Discard items from another account?'),
        content: Text(
          '$count queued item${count == 1 ? '' : 's'} will be deleted from this device and never sent. This cannot be undone.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Keep'),
          ),
          FilledButton(
            style: FilledButton.styleFrom(backgroundColor: AppColors.danger),
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Discard'),
          ),
        ],
      ),
    );
    if (ok == true) {
      await ref.read(outboxRepositoryProvider).deleteOtherUsers(user);
    }
  }
}

/// Inbox app-bar action with a count badge.
class OutboxAction extends ConsumerWidget {
  const OutboxAction({super.key, required this.onPressed});
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final count = ref.watch(outboxBadgeCountProvider);
    final conflicts =
        (ref.watch(outboxItemsProvider).asData?.value ?? const <OutboxItem>[])
            .where((i) => i.isConflict)
            .length;
    return IconButton(
      tooltip: 'Outbox ($count waiting)',
      onPressed: onPressed,
      icon: Badge(
        isLabelVisible: count > 0,
        label: Text('$count'),
        backgroundColor: conflicts > 0 ? AppColors.danger : AppColors.warning,
        child: const Icon(Icons.outbox_outlined),
      ),
    );
  }
}
