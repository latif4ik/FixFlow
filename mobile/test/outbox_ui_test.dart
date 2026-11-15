import 'dart:io';

import 'package:fixflow_tech/app.dart';
import 'package:fixflow_tech/core/api/api_exception.dart';
import 'package:fixflow_tech/core/db/database.dart';
import 'package:fixflow_tech/core/providers.dart';
import 'package:fixflow_tech/core/util/formatters.dart';
import 'package:fixflow_tech/core/widgets/requires_connection.dart';
import 'package:fixflow_tech/features/jobs/caching_jobs_repository.dart';
import 'package:fixflow_tech/features/jobs/job_models.dart';
import 'package:fixflow_tech/features/jobs/jobs_providers.dart';
import 'package:fixflow_tech/features/outbox/outbox_models.dart';
import 'package:fixflow_tech/features/outbox/outbox_providers.dart';
import 'package:fixflow_tech/features/outbox/outbox_repository.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';

import 'support/fixtures.dart';
import 'support/harness.dart';
import 'support/outbox_support.dart';

class _Offline extends SimulateOffline {
  _Offline(this.initial);
  final bool initial;
  @override
  bool build() => initial;
}

Future<AppDatabase> pump(
  WidgetTester t, {
  required FakeJobsRepository repo,
  bool offline = true,
  List<Override> extra = const [],
  Directory? dir,
}) async {
  final base = await baseOverrides(session: technicianSession(), repo: repo);
  late AppDatabase db;
  final root = dir ?? Directory.systemTemp.createTempSync('ff_ui_');
  addTearDown(() {
    if (root.existsSync()) root.deleteSync(recursive: true);
  });
  await t.pumpWidget(
    ProviderScope(
      overrides: [
        ...base,
        simulateOfflineProvider.overrideWith(() => _Offline(offline)),
        outboxRootProvider.overrideWithValue(() async => root),
        ...extra,
      ],
      child: Consumer(
        builder: (context, ref, _) {
          db = ref.watch(appDatabaseProvider);
          return const FixFlowApp();
        },
      ),
    ),
  );
  await t.pumpAndSettle();
  return db;
}

OutboxRepository repoOf(WidgetTester t) =>
    ProviderScope.containerOf(t.element(find.byType(FixFlowApp)))
        .read(outboxRepositoryProvider);

/// Runs [f] inside the fake-async zone, pumping until it completes.
Future<T> inPump<T>(WidgetTester t, Future<T> Function() f) async {
  T? result;
  var done = false;
  Object? error;
  f().then(
    (v) {
      result = v;
      done = true;
    },
    onError: (Object e) {
      error = e;
      done = true;
    },
  );
  for (var i = 0; i < 200 && !done; i++) {
    await t.pump(const Duration(milliseconds: 10));
  }
  if (error != null) throw error!;
  return result as T;
}

Future<void> unmount(WidgetTester t) async {
  await t.pumpWidget(const SizedBox());
  await t.pump(const Duration(milliseconds: 10));
}

FakeJobsRepository repoWithJob() => FakeJobsRepository(
  pages: {
    AssignmentScope.upcoming: [assignment()],
  },
  detail: JobDetail.fromJson(jobJson()),
);

void main() {
  setUpAll(initTimezones);

  testWidgets('composer offline enqueues and shows "Pending sync"', (t) async {
    final db = await pump(t, repo: repoWithJob());
    await seedJob(db);
    await t.tap(find.text('REQ-7'));
    await t.pumpAndSettle();
    expect(
      find.text('Offline - showing data from', skipOffstage: false),
      findsNothing,
    );
    await t.scrollUntilVisible(find.text('New note'), 300);
    await t.tap(find.text('New note'));
    await t.pumpAndSettle();
    expect(
      find.textContaining("You're offline. The note is saved"),
      findsOneWidget,
    );
    await t.enterText(find.byType(TextField), 'Fixed the hinge');
    await t.tap(find.text('Save note (queue offline)'));
    await t.pumpAndSettle();

    expect(find.textContaining('Pending sync · queued '), findsOneWidget);
    expect(find.text('Fixed the hinge'), findsOneWidget);
    expect(find.text('Retry now'), findsOneWidget);
    expect(find.text('Discard'), findsOneWidget);
    final rows = await t.runAsync(() => db.select(db.pendingCommands).get());
    expect(rows!.single.status, 'PENDING');
    expect(rows.single.userId, 'u');
    await unmount(t);
  });

  testWidgets('composer shows a validation message instead of queueing', (
    t,
  ) async {
    final db = await pump(t, repo: repoWithJob());
    await seedJob(db);
    await t.tap(find.text('REQ-7'));
    await t.pumpAndSettle();
    await t.scrollUntilVisible(find.text('New note'), 300);
    await t.tap(find.text('New note'));
    await t.pumpAndSettle();
    await t.tap(find.text('Save note (queue offline)'));
    await t.pumpAndSettle();
    expect(find.text('Write a note first.'), findsOneWidget);
    expect(
      await t.runAsync(() => db.select(db.pendingCommands).get()),
      isEmpty,
    );
    await unmount(t);
  });

  testWidgets('conflict card: reason shown; Discard requires confirmation; '
      'Copy text copies', (t) async {
    final db = await pump(t, repo: repoWithJob());
    await seedJob(db);
    final repo = repoOf(t);
    final item = await inPump(t, () async {
      final i = await repo.enqueueNote(
        orgId: 'o1',
        userId: 'u',
        requestId: 'r1',
        body: 'Stale offline note',
      );
      await repo.markConflict(
        i.commandId,
        OutboxError.reassigned,
        'This job was reassigned, or you no longer have access to it.',
      );
      return i;
    });
    String? copied;
    t.binding.defaultBinaryMessenger.setMockMethodCallHandler(
      SystemChannels.platform,
      (call) async {
        if (call.method == 'Clipboard.setData') {
          copied = (call.arguments as Map)['text'] as String?;
        }
        return null;
      },
    );
    addTearDown(
      () => t.binding.defaultBinaryMessenger.setMockMethodCallHandler(
        SystemChannels.platform,
        null,
      ),
    );

    // Outbox screen via the badge
    await t.tap(find.byIcon(Icons.outbox_outlined));
    await t.pumpAndSettle();
    expect(find.text('Outbox'), findsOneWidget);
    expect(find.text('Stale offline note'), findsOneWidget);
    expect(find.textContaining('Conflict · queued'), findsOneWidget);
    expect(find.textContaining('reassigned'), findsOneWidget);
    expect(find.text('REQ-7'), findsOneWidget);
    expect(find.text('0 waiting to sync · 1 need attention'), findsOneWidget);

    await t.tap(find.text('Copy text'));
    await t.pump();
    expect(copied, 'Stale offline note');

    await t.tap(find.text('Discard draft'));
    await t.pumpAndSettle();
    expect(find.text('Discard draft?'), findsOneWidget);
    await t.tap(find.text('Keep'));
    await t.pumpAndSettle();
    expect(
      (await t.runAsync(() => db.select(db.pendingCommands).get()))!.length,
      1,
      reason: 'cancel must not delete',
    );

    await t.tap(find.text('Discard draft'));
    await t.pumpAndSettle();
    await t.tap(find.widgetWithText(FilledButton, 'Discard'));
    await t.pumpAndSettle();
    expect(
      await t.runAsync(() => db.select(db.pendingCommands).get()),
      isEmpty,
    );
    expect(find.text('Nothing waiting'), findsOneWidget);
    expect(item, isNotNull);
    await unmount(t);
  });

  testWidgets('inbox badge counts queued items', (t) async {
    final db = await pump(t, repo: repoWithJob());
    await seedJob(db);
    expect(find.text('1'), findsNothing);
    final repo = repoOf(t);
    await inPump(t, () async {
      await repo.enqueueNote(
        orgId: 'o1',
        userId: 'u',
        requestId: 'r1',
        body: 'a',
      );
    });
    await t.pumpAndSettle();
    expect(find.text('1'), findsOneWidget); // badge
    await unmount(t);
  });

  testWidgets('offline: cached jobs shown with stale banner', (t) async {
    // Real caching repository over a failing network, cache pre-filled.
    final base = await baseOverrides(session: technicianSession());
    final root = Directory.systemTemp.createTempSync('ff_ui_');
    addTearDown(() => root.deleteSync(recursive: true));
    final overrides = [
      ...base,
      simulateOfflineProvider.overrideWith(() => _Offline(true)),
      outboxRootProvider.overrideWithValue(() async => root),
      jobsRepositoryProvider.overrideWith(
        (ref) => CachingJobsRepository(
          FakeJobsRepository(listError: const NetworkException()),
          ref.watch(appDatabaseProvider),
          () => ref.read(selectedOrgIdProvider),
        ),
      ),
    ];
    late AppDatabase db;
    final container = ProviderContainer(overrides: overrides);
    addTearDown(container.dispose);
    db = container.read(appDatabaseProvider);
    await t.runAsync(() => seedJob(db, status: 'SCHEDULED', scope: 'upcoming'));
    await t.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const FixFlowApp(),
      ),
    );
    await t.pumpAndSettle();
    expect(find.text('REQ-7'), findsOneWidget);
    // seeded fetched_at 04:42Z == 10:42 in Asia/Bishkek
    expect(find.text('Offline - showing data from 10:42'), findsOneWidget);
    await unmount(t);
  });

  testWidgets('RequiresConnection disables its child offline with a reason', (
    t,
  ) async {
    Future<void> build(bool offline) async {
      await t.pumpWidget(
        ProviderScope(
          key: ValueKey(offline),
          overrides: [
            simulateOfflineProvider.overrideWith(() => _Offline(offline)),
            connectivityProvider.overrideWith((ref) => Stream.value(true)),
          ],
          child: MaterialApp(
            home: Scaffold(
              body: RequiresConnection(
                builder: (c, enabled) => FilledButton(
                  onPressed: enabled ? () {} : null,
                  child: const Text('Accept job'),
                ),
              ),
            ),
          ),
        ),
      );
      await t.pump();
    }

    await build(true);
    expect(t.widget<FilledButton>(find.byType(FilledButton)).onPressed, isNull);
    expect(find.textContaining('Requires connection'), findsOneWidget);
    await build(false);
    expect(
      t.widget<FilledButton>(find.byType(FilledButton)).onPressed,
      isNotNull,
    );
    expect(find.textContaining('Requires connection'), findsNothing);
  });

  testWidgets(
    'job detail marks online-only actions as requiring a connection',
    (t) async {
      await pump(t, repo: repoWithJob());
      await t.tap(find.text('REQ-7'));
      await t.pumpAndSettle();
      await t.scrollUntilVisible(find.text('Available actions'), 400);
      // jobJson allows resume (online-only) + add_note (works offline)
      expect(find.textContaining('Requires connection'), findsOneWidget);
      await unmount(t);
    },
  );
}
