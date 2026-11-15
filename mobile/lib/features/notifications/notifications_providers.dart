import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/providers.dart';
import 'notifications_repository.dart';

final notificationsRepositoryProvider = Provider<NotificationsRepository>(
  (ref) => ApiNotificationsRepository(ref.watch(apiClientProvider)),
);

/// How often the unread badge is refreshed while the app is in the foreground
/// and online.
final unreadPollIntervalProvider = Provider<Duration>(
  (ref) => const Duration(seconds: 60),
);

/// Unread notification count. Polling is driven by `NotificationsBell`
/// (a widget-owned timer, so it only runs while the inbox is on screen).
class UnreadCountController extends AsyncNotifier<int> {
  @override
  Future<int> build() async {
    final org = ref.watch(selectedOrgIdProvider);
    final signedIn = ref.watch(
      sessionProvider.select((s) => s.status == SessionStatus.signedIn),
    );
    if (org == null || !signedIn) return 0;
    return ref.read(notificationsRepositoryProvider).unreadCount();
  }

  /// Foreground refresh (app resume / screen open / after mutations).
  void refresh() => ref.invalidateSelf();
}

final unreadCountProvider = AsyncNotifierProvider<UnreadCountController, int>(
  UnreadCountController.new,
);

/// Notification list; mutations update it from the server's answers.
class NotificationsController extends AsyncNotifier<List<NotificationItem>> {
  @override
  Future<List<NotificationItem>> build() {
    ref.watch(selectedOrgIdProvider);
    return ref.read(notificationsRepositoryProvider).list();
  }

  Future<void> refresh() async {
    ref.invalidateSelf();
    await future;
    ref.invalidate(unreadCountProvider);
  }

  /// Throws the repository's `AppException` on failure (state untouched).
  Future<void> markRead(NotificationItem n) async {
    if (!n.unread) return;
    final updated = await ref
        .read(notificationsRepositoryProvider)
        .markRead(n.id);
    final current = state.asData?.value;
    if (current != null) {
      state = AsyncData([for (final i in current) i.id == n.id ? updated : i]);
    }
    ref.invalidate(unreadCountProvider);
  }

  Future<void> markAllRead() async {
    await ref.read(notificationsRepositoryProvider).markAllRead();
    final now = DateTime.now();
    final current = state.asData?.value;
    if (current != null) {
      state = AsyncData([for (final i in current) i.asRead(now)]);
    }
    ref.invalidate(unreadCountProvider);
  }
}

final notificationsProvider =
    AsyncNotifierProvider<NotificationsController, List<NotificationItem>>(
      NotificationsController.new,
    );
