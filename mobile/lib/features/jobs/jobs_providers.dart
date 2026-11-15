import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/providers.dart';
import 'job_models.dart';
import 'jobs_repository.dart';

final jobsRepositoryProvider = Provider<JobsRepository>(
  (ref) => ApiJobsRepository(ref.watch(apiClientProvider)),
);

/// Paginated list state for one inbox tab.
class InboxState {
  const InboxState({
    required this.items,
    required this.total,
    required this.page,
    this.loadingMore = false,
    this.loadMoreError,
  });

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
    final page = await ref
        .read(jobsRepositoryProvider)
        .listAssignments(scope: scope, page: 1, pageSize: pageSize);
    return InboxState(items: page.items, total: page.total, page: 1);
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
  return ref.read(jobsRepositoryProvider).getJob(requestId);
});
