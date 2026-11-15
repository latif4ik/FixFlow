import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/providers.dart';
import '../../core/widgets/state_views.dart';
import 'assignment_card.dart';
import 'job_models.dart';
import 'jobs_providers.dart';

class InboxScreen extends ConsumerWidget {
  const InboxScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final org = ref.watch(sessionProvider.select((s) => s.selectedOrg));
    return DefaultTabController(
      length: AssignmentScope.values.length,
      child: Scaffold(
        appBar: AppBar(
          title: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text('My jobs'),
              if (org != null)
                Text(
                  org.name,
                  style: const TextStyle(
                    fontSize: 12,
                    fontWeight: FontWeight.w400,
                  ),
                ),
            ],
          ),
          actions: [
            IconButton(
              tooltip: 'Profile',
              icon: const Icon(Icons.account_circle_outlined),
              onPressed: () => context.push('/profile'),
            ),
          ],
          bottom: TabBar(
            tabs: [for (final s in AssignmentScope.values) Tab(text: s.label)],
          ),
        ),
        body: TabBarView(
          children: [
            for (final s in AssignmentScope.values)
              InboxList(scope: s, timezone: org?.timezone ?? 'UTC'),
          ],
        ),
      ),
    );
  }
}

class InboxList extends ConsumerWidget {
  const InboxList({super.key, required this.scope, required this.timezone});
  final AssignmentScope scope;
  final String timezone;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final provider = inboxProviderFor(scope);
    final async = ref.watch(provider);
    return async.when(
      loading: () => const LoadingView(label: 'Loading jobs…'),
      error: (e, _) => RefreshIndicator(
        onRefresh: () => ref.read(provider.notifier).refresh(),
        child: ProblemView(error: e, onRetry: () => ref.invalidate(provider)),
      ),
      data: (state) {
        if (state.items.isEmpty) {
          return RefreshIndicator(
            onRefresh: () => ref.read(provider.notifier).refresh(),
            child: LayoutBuilder(
              builder: (context, c) => SingleChildScrollView(
                physics: const AlwaysScrollableScrollPhysics(),
                child: SizedBox(
                  height: c.maxHeight,
                  child: EmptyView(
                    title: 'No ${scope.label.toLowerCase()} jobs',
                    message: switch (scope) {
                      AssignmentScope.upcoming =>
                        'Jobs scheduled for you will appear here.',
                      AssignmentScope.active =>
                        'Jobs you are working on will appear here.',
                      AssignmentScope.history =>
                        'Completed jobs will appear here.',
                    },
                  ),
                ),
              ),
            ),
          );
        }
        return RefreshIndicator(
          onRefresh: () => ref.read(provider.notifier).refresh(),
          child: NotificationListener<ScrollNotification>(
            onNotification: (n) {
              if (n.metrics.extentAfter < 300) {
                ref.read(provider.notifier).loadMore();
              }
              return false;
            },
            child: ListView.separated(
              physics: const AlwaysScrollableScrollPhysics(),
              padding: const EdgeInsets.all(16),
              itemCount: state.items.length + (state.hasMore ? 1 : 0),
              separatorBuilder: (_, _) => const SizedBox(height: 10),
              itemBuilder: (context, i) {
                if (i >= state.items.length) {
                  return Padding(
                    padding: const EdgeInsets.all(12),
                    child: Center(
                      child: state.loadMoreError != null
                          ? TextButton(
                              onPressed: () =>
                                  ref.read(provider.notifier).loadMore(),
                              child: const Text('Could not load more. Retry'),
                            )
                          : const CircularProgressIndicator(),
                    ),
                  );
                }
                final item = state.items[i];
                return AssignmentCard(
                  item: item,
                  timezone: timezone,
                  onTap: () =>
                      context.push('/jobs/${item.requestId}', extra: item),
                );
              },
            ),
          ),
        );
      },
    );
  }
}
