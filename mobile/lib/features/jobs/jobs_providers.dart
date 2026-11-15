import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/providers.dart';
import 'caching_jobs_repository.dart';
import 'job_actions_repository.dart';
import 'job_models.dart';
import 'jobs_repository.dart';

final jobsRepositoryProvider = Provider<JobsRepository>(
  (ref) => CachingJobsRepository(
    ApiJobsRepository(ref.watch(apiClientProvider)),
    ref.watch(appDatabaseProvider),
    () => ref.read(selectedOrgIdProvider),
  ),
);

/// Paginated list state for one inbox tab.
class InboxState {
  const InboxState({
    required this.items,
    required this.total,
    required this.page,
    this.loadingMore = false,
    this.loadMoreError,
    this.stale = false,
    this.syncedAt,
  });

  /// Served from the offline cache (show "Offline - showing data from ...").
  final bool stale;
  final DateTime? syncedAt;

  final List<AssignmentItem> items;
  final int total;
  final int page;
  final bool loadingMore;
  final Object? loadMoreError;

  bool get hasMore => items.length < total;

  InboxState copyWith({
    List<AssignmentItem>? items,
    int? total,
    int? page,
    bool? loadingMore,
    Object? loadMoreError,
    bool clearError = false,
  }) => InboxState(
    items: items ?? this.items,
    total: total ?? this.total,
    page: page ?? this.page,
    loadingMore: loadingMore ?? this.loadingMore,
    loadMoreError: clearError ? null : (loadMoreError ?? this.loadMoreError),
    stale: stale,
    syncedAt: syncedAt,
  );
}

/// One instance per scope tab. Rebuilds (and refetches) when the selected
/// organization changes, so no data leaks across orgs.
class InboxController extends AsyncNotifier<InboxState> {
  InboxController(this.scope);
  final AssignmentScope scope;
  static const pageSize = 20;

  @override
  Future<InboxState> build() async {
    ref.watch(selectedOrgIdProvider);
    // Back online after showing cached data: reload fresh data.
    ref.listen(isOfflineProvider, (prev, next) {
      if (prev == true && next == false && state.asData?.value.stale == true) {
        ref.invalidateSelf();
      }
    });
    final page = await ref
        .read(jobsRepositoryProvider)
        .listAssignments(scope: scope, page: 1, pageSize: pageSize);
    return InboxState(
      items: page.items,
      total: page.total,
      page: 1,
      stale: page.stale,
      syncedAt: page.syncedAt,
    );
  }

  Future<void> refresh() async {
    ref.invalidateSelf();
    await future;
  }

  Future<void> loadMore() async {
    final current = state.asData?.value;
    if (current == null || current.loadingMore || !current.hasMore) return;
    state = AsyncData(current.copyWith(loadingMore: true, clearError: true));
    try {
      final next = await ref
          .read(jobsRepositoryProvider)
          .listAssignments(
            scope: scope,
            page: current.page + 1,
            pageSize: pageSize,
          );
      state = AsyncData(
        current.copyWith(
          items: [...current.items, ...next.items],
          total: next.total,
          page: current.page + 1,
          loadingMore: false,
        ),
      );
    } catch (e) {
      state = AsyncData(current.copyWith(loadingMore: false, loadMoreError: e));
    }
  }
}

final upcomingInboxProvider =
    AsyncNotifierProvider<InboxController, InboxState>(
      () => InboxController(AssignmentScope.upcoming),
    );
final activeInboxProvider = AsyncNotifierProvider<InboxController, InboxState>(
  () => InboxController(AssignmentScope.active),
);
final historyInboxProvider = AsyncNotifierProvider<InboxController, InboxState>(
  () => InboxController(AssignmentScope.history),
);

AsyncNotifierProvider<InboxController, InboxState> inboxProviderFor(
  AssignmentScope scope,
) => switch (scope) {
  AssignmentScope.upcoming => upcomingInboxProvider,
  AssignmentScope.active => activeInboxProvider,
  AssignmentScope.history => historyInboxProvider,
};

/// Job detail by request id; org-scoped.
final jobDetailProvider = FutureProvider.autoDispose.family<JobDetail, String>((
  ref,
  requestId,
) {
  ref.watch(selectedOrgIdProvider);
  ref.listen(isOfflineProvider, (prev, next) {
    if (prev == true && next == false) ref.invalidateSelf();
  });
  return ref.read(jobsRepositoryProvider).getJob(requestId);
});

/// Online-only actions (accept/decline/start/block/resume/complete/materials).
final jobActionsRepositoryProvider = Provider<JobActionsRepository>(
  (ref) => ApiJobActionsRepository(ref.watch(apiClientProvider)),
);

/// Active inventory for the material picker; org-scoped, fetched on demand.
final inventoryProvider = FutureProvider.autoDispose<List<InventoryItem>>((
  ref,
) {
  ref.watch(selectedOrgIdProvider);
  return ref.read(jobActionsRepositoryProvider).inventory();
});

/// Refetches everything a mutation or an app resume can change.
void refreshJobData(
  WidgetRef ref,
  String requestId, {
  bool includeDetail = true,
}) {
  if (includeDetail) ref.invalidate(jobDetailProvider(requestId));
  for (final s in AssignmentScope.values) {
    ref.invalidate(inboxProviderFor(s));
  }
}
