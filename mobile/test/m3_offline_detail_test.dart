import 'dart:convert';

import 'package:drift/drift.dart' show Value;
import 'package:drift/native.dart';
import 'package:fixflow_tech/app.dart';
import 'package:fixflow_tech/core/api/api_client.dart';
import 'package:fixflow_tech/core/api/api_exception.dart';
import 'package:fixflow_tech/core/db/database.dart';
import 'package:fixflow_tech/core/providers.dart';
import 'package:fixflow_tech/core/util/formatters.dart';
import 'package:fixflow_tech/features/jobs/caching_jobs_repository.dart';
import 'package:fixflow_tech/features/jobs/job_models.dart';
import 'package:fixflow_tech/features/jobs/jobs_providers.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/fake_adapter.dart';
import 'support/fixtures.dart';
import 'support/harness.dart';
import 'support/m3_support.dart';

/// Real caching repository + real ApiClient chain (incl. the simulated-offline
/// interceptor): offline detail must come from the cache, not hang.
void main() {
  setUpAll(initTimezones);

  test('detail is served from cache while simulated offline', () async {
    final adapter = FakeAdapter(
      (o) => throw StateError('no request may leave while offline: ${o.uri}'),
    );
    final base = await baseOverrides(session: technicianSession());
    final container = ProviderContainer(
      overrides: [
        ...base,
        simulateOfflineProvider.overrideWith(() => OfflineSwitch(true)),
        dioProvider.overrideWith(
          (ref) => ApiClient.buildDio(
            baseUrl: 'http://fake',
            authContext: () => (token: 't', orgId: 'o1'),
            adapter: adapter,
          ),
        ),
      ],
    );
    addTearDown(container.dispose);
    final db = container.read(appDatabaseProvider);
    await db
        .into(db.cachedJobs)
        .insert(
          CachedJobsCompanion.insert(
            orgId: 'o1',
            requestId: 'r1',
            scope: const Value('active'),
            itemJson: Value(jsonEncode(assignmentJson(status: 'IN_PROGRESS'))),
            detailJson: Value(jsonEncode(jobJson())),
            fetchedAt: DateTime.utc(2026, 11, 15, 4, 42),
          ),
        );
    final job = await container
        .read(jobDetailProvider('r1').future)
        .timeout(const Duration(seconds: 5));
    expect(job.stale, isTrue);
    expect(job.title, 'Repair the stuck service door');
    expect(adapter.requests, isEmpty);
  });

  test(
    'a job that left a scope keeps its cached detail, others are pruned',
    () async {
      final db = AppDatabase(NativeDatabase.memory());
      addTearDown(db.close);
      Future<void> seed(String id, {required bool detail}) => db
          .into(db.cachedJobs)
          .insert(
            CachedJobsCompanion.insert(
              orgId: 'o1',
              requestId: id,
              scope: const Value('upcoming'),
              itemJson: Value(jsonEncode(assignmentJson(id: id))),
              detailJson: Value(
                detail ? jsonEncode(jobJson()..['id'] = id) : null,
              ),
              fetchedAt: DateTime.utc(2026, 11, 15),
            ),
          );
      await seed('moved', detail: true);
      await seed('gone', detail: false);
      // Upcoming is now empty (the job was accepted/started, another vanished).
      final online = CachingJobsRepository(
        FakeJobsRepository(pages: {AssignmentScope.upcoming: []}),
        db,
        () => 'o1',
      );
      await online.listAssignments(scope: AssignmentScope.upcoming);
      final offline = CachingJobsRepository(
        FakeJobsRepository(
          listError: const NetworkException(),
          detailError: const NetworkException(),
        ),
        db,
        () => 'o1',
      );
      final rows = await db.select(db.cachedJobs).get();
      expect(rows.map((r) => r.requestId), ['moved']);
      expect(rows.single.itemJson, isNull);
      expect((await offline.getJob('moved')).stale, isTrue);
      final list = await offline.listAssignments(
        scope: AssignmentScope.upcoming,
      );
      expect(list.items, isEmpty); // no ghost entry in the inbox
    },
  );

  group('offline banner recovery', () {
    testWidgets(
      'server unreachable (not simulated): Retry probes and recovers',
      (t) async {
        final adapter = FakeAdapter(
          (o) => FakeAdapter.json(200, {'status': 'ok'}),
        );
        await pumpM3(
          t,
          detail: detailWith(actions: ['accept', 'decline', 'add_note']),
          extra: [
            dioProvider.overrideWith(
              (ref) => ApiClient.buildDio(
                baseUrl: 'http://fake',
                authContext: () => (token: 't', orgId: 'o1'),
                adapter: adapter,
                onNetworkResult: (ok) =>
                    ref.read(networkReachableProvider.notifier).report(ok),
              ),
            ),
          ],
        );
        final container = ProviderScope.containerOf(
          t.element(find.byType(FixFlowApp)),
        );
        container.read(networkReachableProvider.notifier).report(false);
        await t.pump();
        expect(find.textContaining("You're offline"), findsOneWidget);
        adapter.requests.clear();
        await t.tap(find.text('Retry'));
        await t.pumpAndSettle();
        expect(
          adapter.requests.map((o) => o.path),
          contains(endsWith('/health/live')),
        );
        expect(find.textContaining("You're offline"), findsNothing);
        await unmountApp(t);
      },
    );

    testWidgets('simulated offline has no Retry (it is a demo switch)', (
      t,
    ) async {
      await pumpM3(
        t,
        offline: true,
        detail: detailWith(actions: ['accept', 'decline', 'add_note']),
      );
      expect(find.textContaining("You're offline"), findsOneWidget);
      expect(find.text('Retry'), findsNothing);
      await unmountApp(t);
    });
  });
}
