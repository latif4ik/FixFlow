import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/api/api_exception.dart';
import '../../core/providers.dart';
import '../../core/theme/app_theme.dart';
import '../../core/util/formatters.dart';
import '../../core/widgets/state_views.dart';
import 'notifications_providers.dart';
import 'notifications_repository.dart';

IconData notificationIcon(String type) => switch (type) {
  'ASSIGNMENT_CREATED' => Icons.assignment_ind_outlined,
  'ASSIGNMENT_REMOVED' => Icons.person_remove_outlined,
  'ASSIGNMENT_RESCHEDULED' => Icons.event_repeat,
  'ESTIMATE_APPROVED' => Icons.thumb_up_alt_outlined,
  'ESTIMATE_REJECTED' => Icons.thumb_down_alt_outlined,
  'STATUS_CHANGED' => Icons.swap_horiz,
  _ => Icons.notifications_none,
};

/// Bell for the inbox app bar with an unread badge. Polls the unread count
/// every [unreadPollIntervalProvider] while it is on screen, the app is in the
/// foreground and the device is online.
class NotificationsBell extends ConsumerStatefulWidget {
  const NotificationsBell({super.key, required this.onPressed});
  final VoidCallback onPressed;

  @override
  ConsumerState<NotificationsBell> createState() => _NotificationsBellState();
}

class _NotificationsBellState extends ConsumerState<NotificationsBell> {
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    _timer = Timer.periodic(ref.read(unreadPollIntervalProvider), (_) {
      final state = WidgetsBinding.instance.lifecycleState;
      final foreground = state == null || state == AppLifecycleState.resumed;
      // Gated on the radio / dev switch, NOT on the last failed request, so a
      // successful poll also lets the app recover from a blip.
      final canTry =
          !ref.read(simulateOfflineProvider) &&
          (ref.read(connectivityProvider).asData?.value ?? true);
      if (foreground && canTry) ref.invalidate(unreadCountProvider);
    });
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final count = ref.watch(unreadCountProvider).asData?.value ?? 0;
    return IconButton(
      tooltip: count > 0 ? 'Notifications, $count unread' : 'Notifications',
      onPressed: widget.onPressed,
      icon: Badge(
        isLabelVisible: count > 0,
        label: Text(count > 99 ? '99+' : '$count'),
        child: const Icon(Icons.notifications_outlined),
      ),
    );
  }
}

class NotificationsScreen extends ConsumerWidget {
  const NotificationsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final tz = ref.watch(
      sessionProvider.select((s) => s.selectedOrg?.timezone ?? 'UTC'),
    );
    final async = ref.watch(notificationsProvider);
    final hasUnread = async.asData?.value.any((n) => n.unread) ?? false;
    return Scaffold(
      appBar: AppBar(
        title: const Text('Notifications'),
        actions: [
          TextButton(
            onPressed: hasUnread ? () => _markAll(context, ref) : null,
            child: const Text('Mark all read'),
          ),
        ],
      ),
      body: async.when(
        loading: () => const LoadingView(label: 'Loading notifications…'),
        error: (e, _) => ProblemView(
          error: e,
          onRetry: () => ref.invalidate(notificationsProvider),
        ),
        data: (items) => RefreshIndicator(
          onRefresh: () => ref.read(notificationsProvider.notifier).refresh(),
          child: items.isEmpty
              ? LayoutBuilder(
                  builder: (context, c) => SingleChildScrollView(
                    physics: const AlwaysScrollableScrollPhysics(),
                    child: SizedBox(
                      height: c.maxHeight,
                      child: const EmptyView(
                        icon: Icons.notifications_none,
                        title: 'No notifications',
                        message: 'New assignments and schedule changes show up here.',
                      ),
                    ),
                  ),
                )
              : ListView.separated(
                  physics: const AlwaysScrollableScrollPhysics(),
                  padding: const EdgeInsets.all(16),
                  itemCount: items.length,
                  separatorBuilder: (_, _) => const SizedBox(height: 8),
                  itemBuilder: (context, i) => NotificationTile(
                    item: items[i],
                    timezone: tz,
                    onTap: () => _open(context, ref, items[i]),
                  ),
                ),
        ),
      ),
    );
  }

  Future<void> _markAll(BuildContext context, WidgetRef ref) async {
    final messenger = ScaffoldMessenger.of(context);
    try {
      await ref.read(notificationsProvider.notifier).markAllRead();
    } on AppException catch (e) {
      messenger.showSnackBar(
        SnackBar(content: Text('Could not mark as read: ${e.message}')),
      );
    }
  }

  Future<void> _open(
    BuildContext context,
    WidgetRef ref,
    NotificationItem n,
  ) async {
    final messenger = ScaffoldMessenger.of(context);
    try {
      await ref.read(notificationsProvider.notifier).markRead(n);
    } on AppException catch (e) {
      messenger.showSnackBar(
        SnackBar(content: Text('Could not mark as read: ${e.message}')),
      );
    }
    // The job may no longer be visible (removed assignment); the detail
    // screen explains that instead of failing silently.
    if (n.requestId != null && context.mounted) {
      context.push('/jobs/${n.requestId}');
    }
  }
}

class NotificationTile extends StatelessWidget {
  const NotificationTile({
    super.key,
    required this.item,
    required this.timezone,
    required this.onTap,
  });
  final NotificationItem item;
  final String timezone;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final unread = item.unread;
    return Card(
      color: unread ? AppColors.primaryTint : null,
      child: InkWell(
        borderRadius: BorderRadius.circular(AppRadius.md),
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Icon(
                notificationIcon(item.type),
                color: unread ? AppColors.primary : AppColors.muted,
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        if (unread) ...[
                          const Icon(
                            Icons.circle,
                            size: 8,
                            color: AppColors.primary,
                          ),
                          const SizedBox(width: 6),
                          const Text(
                            'Unread',
                            style: TextStyle(
                              fontSize: 11,
                              fontWeight: FontWeight.w700,
                              color: AppColors.primaryDark,
                            ),
                          ),
                        ] else
                          const Text(
                            'Read',
                            style: TextStyle(
                              fontSize: 11,
                              color: AppColors.muted,
                            ),
                          ),
                      ],
                    ),
                    const SizedBox(height: 2),
                    Text(
                      item.title,
                      style: TextStyle(
                        fontWeight: unread ? FontWeight.w700 : FontWeight.w500,
                      ),
                    ),
                    Text(item.body),
                    const SizedBox(height: 4),
                    Text(
                      formatDateTime(item.createdAt, timezone),
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
      ),
    );
  }
}
