import 'dart:convert';
import 'dart:io';

import 'package:drift/drift.dart' show driftRuntimeOptions;
import 'package:drift/native.dart';
import 'package:fixflow_tech/core/api/api_exception.dart';
import 'package:fixflow_tech/core/db/database.dart';
import 'package:fixflow_tech/features/jobs/caching_jobs_repository.dart';
import 'package:fixflow_tech/features/jobs/job_models.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/fixtures.dart';
import 'support/harness.dart';

class _Toggle extends FakeJobsRepository {
  _Toggle({super.pages, super.detail});
  bool offline = false;
  Object? detailFailure;

  @override
  Future<AssignmentPage> listAssignments({
    required AssignmentScope scope,
    int page = 1,
    int pageSize = 20,
  }) {
    if (offline) throw const NetworkException();
    return super.listAssignments(scope: scope, page: page, pageSize: pageSize);
  }

  @override
  Future<JobDetail> getJob(String requestId) async {
    if (offline) throw const NetworkException();
    if (detailFailure != null) throw detailFailure!;
    return detail!;
  }
}

void main() {
  late AppDatabase db;
  setUp(() => db = AppDatabase(NativeDatabase.memory()));
  tearDown(() => db.close());

  group('CachingJobsRepository', () {
    test(
      'online write-through, offline served from cache with stale flag',
      () async {
        final inner = _Toggle(
          pages: {
            AssignmentScope.upcoming: [
              assignment(),
              assignment(id: 'r2', display: 'REQ-8'),
            ],
          },
          detail: JobDetail.fromJson(jobJson()),
        );
        var org = 'o1';
        final now = DateTime.utc(2026, 11, 15, 4, 42);
        final repo = CachingJobsRepository(
          inner,
          db,
          () => org,
          clock: () => now,
        );

        final live = await repo.listAssignments(
          scope: AssignmentScope.upcoming,
        );
        expect(live.stale, isFalse);
        await repo.getJob('r1');

        inner.offline = true;
        final cached = await repo.listAssignments(
          scope: AssignmentScope.upcoming,
        );
        expect(cached.stale, isTrue);
        expect(cached.syncedAt!.toUtc(), now);
        expect(
          cached.items.map((i) => i.displayId),
          unorderedEquals(['REQ-7', 'REQ-8']),
        );
        expect(cached.items.first.allowedActions, contains('add_note'));
        final job = await repo.getJob('r1');
        expect(job.stale, isTrue);
        expect(job.title, 'Repair the stuck service door');
        expect(job.notes.single.body, 'Waiting for a replacement hinge.');

        // never fetched detail for r2 -> offline error, not fake data
        await expectLater(repo.getJob('r2'), throwsA(isA<NetworkException>()));
        // page 2 offline: nothing more
        final p2 = await repo.listAssignments(
          scope: AssignmentScope.upcoming,
          page: 2,
        );
        expect(p2.items, isEmpty);
      },
    );

    test(
      'cache is scoped by organization (no leakage on org switch)',
      () async {
        final inner = _Toggle(
          pages: {
            AssignmentScope.active: [assignment()],
          },
        );
        var org = 'o1';
        final repo = CachingJobsRepository(inner, db, () => org);
        await repo.listAssignments(scope: AssignmentScope.active);
        inner.offline = true;
        org = 'o2';
        // nothing cached for o2: surfaces the offline error, shows no o1 data
        await expectLater(
          repo.listAssignments(scope: AssignmentScope.active),
          throwsA(isA<NetworkException>()),
        );
        org = 'o1';
        expect(
          (await repo.listAssignments(scope: AssignmentScope.active)).items,
          hasLength(1),
        );
      },
    );

    test(
      'empty scope with other cached data returns an empty stale page',
      () async {
        final inner = _Toggle(
          pages: {
            AssignmentScope.active: [assignment()],
          },
        );
        final repo = CachingJobsRepository(inner, db, () => 'o1');
        await repo.listAssignments(scope: AssignmentScope.active);
        inner.offline = true;
        final h = await repo.listAssignments(scope: AssignmentScope.history);
        expect(h.items, isEmpty);
        expect(h.stale, isTrue);
      },
    );

    test('a fresh complete listing removes jobs that left the scope', () async {
      final inner = _Toggle(
        pages: {
          AssignmentScope.upcoming: [
            assignment(),
            assignment(id: 'r2', display: 'REQ-8'),
          ],
        },
      );
      final repo = CachingJobsRepository(inner, db, () => 'o1');
      await repo.listAssignments(scope: AssignmentScope.upcoming);
      final inner2 = _Toggle(
        pages: {
          AssignmentScope.upcoming: [assignment()],
        },
      );
      await CachingJobsRepository(
        inner2,
        db,
        () => 'o1',
      ).listAssignments(scope: AssignmentScope.upcoming);
      expect((await db.select(db.cachedJobs).get()).map((r) => r.requestId), [
        'r1',
      ]);
    });

    test('history is capped', () async {
      final items = [
        for (var i = 0; i < CachingJobsRepository.historyCap + 10; i++)
          assignment(id: 'h$i', display: 'REQ-$i'),
      ];
      final inner = _Toggle(pages: {AssignmentScope.history: items});
      final repo = CachingJobsRepository(inner, db, () => 'o1');
      await repo.listAssignments(scope: AssignmentScope.history, pageSize: 100);
      expect(
        (await db.select(db.cachedJobs).get()).length,
        CachingJobsRepository.historyCap,
      );
    });

    test('404 on detail evicts the cached job (no longer assigned)', () async {
      final inner = _Toggle(
        pages: {
          AssignmentScope.active: [assignment()],
        },
        detail: JobDetail.fromJson(jobJson()),
      );
      final repo = CachingJobsRepository(inner, db, () => 'o1');
      await repo.listAssignments(scope: AssignmentScope.active);
      inner.detailFailure = apiError(404);
      await expectLater(repo.getJob('r1'), throwsA(isA<ApiException>()));
      expect(await db.select(db.cachedJobs).get(), isEmpty);
    });
  });

  test('migration v1 -> v2 keeps data and adds user_id / error_code', () async {
    driftRuntimeOptions.dontWarnAboutMultipleDatabases = true;
    final dir = Directory.systemTemp.createTempSync('ff_mig_');
    addTearDown(() => dir.deleteSync(recursive: true));
    final file = File('${dir.path}/v1.sqlite');
    final v1 = AppDatabase(
      NativeDatabase(
        file,
        setup: (raw) {
          raw.execute('''
CREATE TABLE pending_commands (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  client_command_id TEXT NOT NULL UNIQUE,
  org_id TEXT NOT NULL, request_id TEXT NOT NULL, type TEXT NOT NULL,
  payload_json TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'PENDING',
  attempts INTEGER NOT NULL DEFAULT 0, last_error TEXT,
  next_attempt_at INTEGER, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL);
INSERT INTO pending_commands (client_command_id, org_id, request_id, type, payload_json, created_at, updated_at)
VALUES ('c1','o1','r1','NOTE','{"body":"old","visibility":"PUBLIC","label":"REQ-1"}', 1, 1);
PRAGMA user_version = 1;''');
        },
      ),
    );
    final cols = await v1
        .customSelect('PRAGMA table_info(pending_commands)')
        .get();
    final names = cols.map((r) => r.read<String>('name')).toSet();
    expect(names, containsAll(['user_id', 'error_code']));
    final row = (await v1.select(v1.pendingCommands).get()).single;
    expect(row.clientCommandId, 'c1');
    expect(row.userId, ''); // legacy rows have no owner -> never replayed
    expect(row.errorCode, isNull);
    expect(jsonDecode(row.payloadJson)['body'], 'old');
    await v1.close();
  });
}
