import 'dart:io';
import 'dart:math';

import 'package:drift/drift.dart' show driftRuntimeOptions;
import 'package:drift/native.dart';
import 'package:fixflow_tech/core/db/database.dart';
import 'package:fixflow_tech/features/outbox/outbox_models.dart';
import 'package:fixflow_tech/features/outbox/outbox_repository.dart';
import 'package:fixflow_tech/features/outbox/sync_engine.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/outbox_support.dart';

void main() {
  late AppDatabase db;
  late Rig rig;

  setUp(() async {
    db = AppDatabase(NativeDatabase.memory());
    await seedJob(db);
    rig = Rig.create(db);
  });
  tearDown(() async {
    rig.dispose();
    await db.close();
  });

  group('enqueue', () {
    test('writes command + attachments atomically, copies files', () async {
      final item = await rig.enqueue(photos: 2);
      expect(item.status, OutboxStatus.pending);
      expect(item.photos.length, 2);
      expect(item.visibility, 'PUBLIC');
      expect(item.requestLabel, 'REQ-7');
      for (final p in item.photos) {
        expect(File(p.localPath).existsSync(), isTrue);
        expect(
          p.localPath,
          contains('outbox/${item.commandId}/${p.position}.png'),
        );
      }
      expect((await db.select(db.pendingCommands).get()).single.type, 'NOTE');
      expect((await db.select(db.pendingAttachments).get()).length, 2);
      expect(item.commandId.length, 36); // uuid v4
    });

    test('rejects an image larger than 10 MiB and leaves no trace', () async {
      final big = writeImage(rig.dir, 'big.png', [
        ...tinyPng,
        ...List.filled(OutboxRepository.maxPhotoBytes, 0),
      ]);
      await expectLater(
        rig.repo.enqueueNote(
          orgId: 'o1',
          userId: 'u1',
          requestId: 'r1',
          body: 'x',
          images: [PickedImage(path: big.path)],
        ),
        throwsA(
          isA<OutboxRejected>().having(
            (e) => e.message,
            'message',
            contains('larger than 10 MB'),
          ),
        ),
      );
      expect(await db.select(db.pendingCommands).get(), isEmpty);
      expect(Directory('${rig.dir.path}/outbox').existsSync(), isFalse);
    });

    test('rejects a non-image / unsupported type', () async {
      final txt = writeImage(rig.dir, 'a.png', 'not an image'.codeUnits);
      await expectLater(
        rig.repo.enqueueNote(
          orgId: 'o1',
          userId: 'u1',
          requestId: 'r1',
          body: 'x',
          images: [PickedImage(path: txt.path)],
        ),
        throwsA(
          isA<OutboxRejected>().having(
            (e) => e.message,
            'message',
            contains('JPEG, PNG or WebP'),
          ),
        ),
      );
      expect(await db.select(db.pendingCommands).get(), isEmpty);
    });

    test(
      'rejects empty body, uncached job, non-ACTIVE assignment, closed',
      () async {
        Future<void> expectRejected(Future<Object?> f, String part) =>
            expectLater(
              f,
              throwsA(
                isA<OutboxRejected>().having(
                  (e) => e.message,
                  'message',
                  contains(part),
                ),
              ),
            );
        await expectRejected(
          rig.repo.enqueueNote(
            orgId: 'o1',
            userId: 'u1',
            requestId: 'r1',
            body: '  ',
          ),
          'Write a note',
        );
        await expectRejected(
          rig.repo.enqueueNote(
            orgId: 'o1',
            userId: 'u1',
            requestId: 'unknown',
            body: 'x',
          ),
          'not available offline',
        );
        await seedJob(db, id: 'r2', assignmentStatus: 'DECLINED');
        await expectRejected(
          rig.repo.enqueueNote(
            orgId: 'o1',
            userId: 'u1',
            requestId: 'r2',
            body: 'x',
          ),
          'no longer assigned',
        );
        await seedJob(db, id: 'r3', status: 'CLOSED');
        await expectRejected(
          rig.repo.enqueueNote(
            orgId: 'o1',
            userId: 'u1',
            requestId: 'r3',
            body: 'x',
          ),
          'closed',
        );
        // other org's cache is not usable
        await expectRejected(
          rig.repo.enqueueNote(
            orgId: 'o2',
            userId: 'u1',
            requestId: 'r1',
            body: 'x',
          ),
          'not available offline',
        );
      },
    );
  });

  test(
    'queue survives a simulated restart; SYNCING is reset to PENDING',
    () async {
      driftRuntimeOptions.dontWarnAboutMultipleDatabases = true;
      final dir = Directory.systemTemp.createTempSync('ff_restart_');
      addTearDown(() => dir.deleteSync(recursive: true));
      final file = File('${dir.path}/app.sqlite');
      var fileDb = AppDatabase(NativeDatabase(file));
      await seedJob(fileDb);
      var r = Rig.create(fileDb, dir: dir);
      final item = await r.enqueue(photos: 1, body: 'survives');
      await r.repo.markSyncing(item.commandId); // process "killed" mid-sync
      await fileDb.close();

      fileDb = AppDatabase(NativeDatabase(file)); // new process
      addTearDown(fileDb.close);
      r = Rig.create(fileDb, dir: dir);
      var again = (await r.repo.all()).single;
      expect(again.status, OutboxStatus.syncing);
      expect(await r.repo.resetSyncing(), 1);
      again = (await r.repo.all()).single;
      expect(again.status, OutboxStatus.pending);
      expect(again.body, 'survives');
      expect(again.commandId, item.commandId);
      expect(File(again.photos.single.localPath).existsSync(), isTrue);
      // ... and it is delivered after the restart.
      final report = await r.engine.runOnce();
      expect(report.synced, 1);
      expect(r.server.notes.keys, [item.commandId]);
    },
  );

  group('sync engine', () {
    test('happy path: uploads photo, posts note with ids, cleans up', () async {
      final item = await rig.enqueue(photos: 2);
      final report = await rig.engine.runOnce();
      expect(report.outcome, SyncOutcome.completed);
      expect(report.synced, 1);
      expect(report.syncedRequestIds, {'r1'});
      expect(rig.server.files.length, 2);
      final note = rig.server.notes[item.commandId]!;
      expect(note['attachment_ids'], ['file-1', 'file-2']);
      expect(note['visibility'], 'PUBLIC');
      expect(await db.select(db.pendingCommands).get(), isEmpty);
      expect(await db.select(db.pendingAttachments).get(), isEmpty);
      expect(
        Directory('${rig.dir.path}/outbox/${item.commandId}').existsSync(),
        isFalse,
      );
    });

    test(
      'idempotent replay: note accepted but response lost -> retry gets 200, '
      'ONE note, photo uploaded once',
      () async {
        final item = await rig.enqueue(photos: 1);
        rig.server.dropNoteResponseOnce = true;
        final first = await rig.engine.runOnce();
        expect(first.outcome, SyncOutcome.networkDown);
        var row = (await rig.repo.all()).single;
        expect(row.status, OutboxStatus.pending);
        expect(row.attempts, 1);
        expect(row.photos.single.uploaded, isTrue); // id persisted at once
        expect(rig.server.notes.length, 1); // server DID accept it

        final second = await rig.engine.runOnce(force: true);
        expect(second.synced, 1);
        expect(rig.server.notes.length, 1);
        expect(rig.server.noteRequests, 2);
        expect(rig.server.fileRequests, 1); // not re-uploaded
        expect(rig.server.files.length, 1);
        expect(await rig.repo.all(), isEmpty);
        expect(item.commandId, rig.server.notes.keys.single);
      },
    );

    test('even if the file id was lost (crash), re-upload is deduped by '
        '(command id, index)', () async {
      await rig.enqueue(photos: 1);
      rig.server.dropNoteResponseOnce = true;
      await rig.engine.runOnce();
      // Simulate a crash before the uploaded id was persisted.
      await db.customStatement(
        'UPDATE pending_attachments SET uploaded_file_id = NULL, status = ?',
        ['PENDING'],
      );
      await rig.engine.runOnce(force: true);
      expect(rig.server.fileRequests, 2); // sent again ...
      expect(rig.server.files.length, 1); // ... but ONE server file row
      expect(rig.server.notes.length, 1);
      expect(await rig.repo.all(), isEmpty);
    });

    test(
      '404 -> CONFLICT with reason; draft + files kept; not retried',
      () async {
        final item = await rig.enqueue(photos: 1);
        rig.server.rejectNoteWith = 404;
        final report = await rig.engine.runOnce();
        expect(report.conflicts, 1);
        final row = (await rig.repo.all()).single;
        expect(row.status, OutboxStatus.conflict);
        expect(row.errorCode, OutboxError.reassigned);
        expect(row.lastError, contains('reassigned'));
        expect(row.body, 'Replaced the lamp');
        expect(File(row.photos.single.localPath).existsSync(), isTrue);
        // A conflict is not replayed automatically.
        final before = rig.server.allRequests;
        await rig.engine.runOnce(force: true);
        expect(rig.server.allRequests, before);
        expect(rig.server.notes, isEmpty);
        expect(item.commandId, row.commandId);
      },
    );

    test(
      '409 closed -> CONFLICT (closed); idempotency_key_reused -> no retry',
      () async {
        await rig.enqueue();
        rig.server
          ..rejectNoteWith = 409
          ..rejectCode = 'invalid_transition'
          ..rejectMessage = 'Request is closed.';
        await rig.engine.runOnce();
        var row = (await rig.repo.all()).single;
        expect(row.status, OutboxStatus.conflict);
        expect(row.errorCode, OutboxError.closed);
        expect(row.lastError, contains('closed'));
        expect(row.retryMeaningful, isTrue);

        await rig.repo.retry(row.commandId);
        rig.server
          ..rejectCode = 'idempotency_key_reused'
          ..rejectMessage = 'x';
        await rig.engine.runOnce(force: true);
        row = (await rig.repo.all()).single;
        expect(row.errorCode, OutboxError.idempotencyReused);
        expect(row.retryMeaningful, isFalse);
      },
    );

    test('413/422 on a photo -> CONFLICT "Photo rejected by server"', () async {
      await rig.enqueue(photos: 1);
      rig.server
        ..rejectFileWith = 422
        ..rejectMessage = 'Unsupported image.';
      await rig.engine.runOnce();
      final row = (await rig.repo.all()).single;
      expect(row.status, OutboxStatus.conflict);
      expect(row.lastError, 'Photo rejected by server: Unsupported image.');
      expect(row.photos.length, 1); // never dropped silently
      expect(rig.server.noteRequests, 0);
    });

    test('network error -> PENDING, attempts+1, exponential backoff', () async {
      await rig.enqueue();
      rig.server.networkDown = true;
      final r1 = await rig.engine.runOnce();
      expect(r1.outcome, SyncOutcome.networkDown);
      var row = (await rig.repo.all()).single;
      expect(row.status, OutboxStatus.pending);
      expect(row.attempts, 1);
      expect(row.lastError, isNotNull);
      final wait1 = row.nextAttemptAt!.difference(rig.clock.now());
      expect(wait1, greaterThan(Duration.zero));
      expect(wait1, lessThanOrEqualTo(const Duration(seconds: 5)));

      // Not due yet: a periodic (non-forced) run sends nothing.
      final n = rig.server.allRequests;
      await rig.engine.runOnce();
      expect(rig.server.allRequests, n);

      rig.advance(const Duration(seconds: 6));
      await rig.engine.runOnce();
      row = (await rig.repo.all()).single;
      expect(row.attempts, 2);
      final wait2 = row.nextAttemptAt!.difference(rig.clock.now());
      expect(wait2, greaterThan(wait1)); // grew
    });

    test('backoff is exponential with jitter and capped at 5 minutes', () {
      final rnd = Random(1);
      final secs = [
        for (var a = 1; a <= 12; a++)
          OutboxRepository.backoff(a, rnd).inMilliseconds / 1000,
      ];
      expect(secs[0], inInclusiveRange(4, 5));
      expect(secs[1], inInclusiveRange(8, 10));
      expect(secs[2], inInclusiveRange(16, 20));
      expect(secs.last, lessThanOrEqualTo(300));
      expect(secs.last, greaterThan(239));
    });

    test('5xx / 429 are retryable (PENDING), not conflicts', () async {
      await rig.enqueue();
      rig.server
        ..rejectNoteWith = 503
        ..rejectCode = 'unavailable';
      final r = await rig.engine.runOnce();
      expect(r.retries, 1);
      final row = (await rig.repo.all()).single;
      expect(row.status, OutboxStatus.pending);
      expect(row.attempts, 1);
    });

    test('401 stops the run and keeps the whole queue', () async {
      await rig.enqueue(body: 'one');
      await rig.enqueue(body: 'two', request: 'r1');
      rig.server
        ..rejectNoteWith = 401
        ..rejectCode = 'unauthorized';
      final report = await rig.engine.runOnce();
      expect(report.outcome, SyncOutcome.unauthorized);
      expect(rig.server.noteRequests, 1); // second not attempted
      final rows = await rig.repo.all();
      expect(rows.map((r) => r.status), [
        OutboxStatus.pending,
        OutboxStatus.pending,
      ]);
      expect(rows.first.attempts, 0);
    });

    test("another user's commands are never replayed", () async {
      await rig.enqueue(body: 'mine');
      await rig.enqueue(body: 'theirs', user: 'u2');
      final report = await rig.engine.runOnce();
      expect(report.synced, 1);
      expect(rig.server.notes.values.single['body'], 'mine');
      final left = (await rig.repo.all()).single;
      expect(left.body, 'theirs');
      expect(left.userId, 'u2');
      expect(await rig.repo.watchOtherUsersCount('u1').first, 1);
      await rig.repo.deleteOtherUsers('u1');
      expect(await rig.repo.all(), isEmpty);
    });

    test('only the selected organization is processed', () async {
      await rig.enqueue();
      final other = Rig.create(db, dir: rig.dir, org: 'o2');
      final report = await other.engine.runOnce();
      expect(report.synced, 0);
      expect(other.server.allRequests, 0);
      expect((await rig.repo.all()).length, 1);
    });

    test('no request is sent while offline / simulated offline', () async {
      var online = false;
      final r = Rig.create(db, dir: rig.dir, canSync: () => online);
      await rig.enqueue();
      final off = await r.engine.runOnce();
      expect(off.outcome, SyncOutcome.skipped);
      expect(r.server.allRequests, 0);
      online = true;
      expect((await r.engine.runOnce()).synced, 1);
    });

    test('single-flight: concurrent runs do not duplicate requests', () async {
      await rig.enqueue(photos: 1);
      final results = await Future.wait([
        rig.engine.runOnce(),
        rig.engine.runOnce(),
        rig.engine.runOnce(),
      ]);
      expect(results.where((r) => r.synced == 1).length, 1);
      expect(rig.server.noteRequests, 1);
      expect(rig.server.fileRequests, 1);
      expect(rig.server.notes.length, 1);
    });

    test('FIFO per request: a retryable failure blocks later notes of that '
        'request only', () async {
      await seedJob(db, id: 'r9');
      await rig.enqueue(body: 'first');
      await rig.enqueue(body: 'second');
      await rig.enqueue(body: 'other job', request: 'r9');
      rig.server
        ..rejectNoteWith = 500
        ..rejectCode = 'boom';
      // every note POST answers 500
      final report = await rig.engine.runOnce();
      expect(report.retries, greaterThanOrEqualTo(1));
      final bodies = rig.server.noteRequests;
      // r1 'first' failed -> 'second' skipped; 'other job' attempted too (500).
      expect(bodies, 2);
      final rows = await rig.repo.all();
      expect(rows.firstWhere((r) => r.body == 'second').attempts, 0);
    });

    test('queued commands are sent in FIFO order', () async {
      await rig.enqueue(body: 'a');
      await rig.enqueue(body: 'b');
      await rig.enqueue(body: 'c');
      await rig.engine.runOnce();
      expect(rig.server.notes.values.map((n) => n['body']), ['a', 'b', 'c']);
    });

    test('missing local photo -> CONFLICT, draft kept', () async {
      final item = await rig.enqueue(photos: 1);
      File(item.photos.single.localPath).deleteSync();
      await rig.engine.runOnce();
      final row = (await rig.repo.all()).single;
      expect(row.status, OutboxStatus.conflict);
      expect(row.errorCode, OutboxError.photoMissing);
      expect(rig.server.allRequests, 0);
    });
  });

  test('delete removes rows and local files', () async {
    final item = await rig.enqueue(photos: 1);
    await rig.repo.delete(item.commandId);
    expect(await rig.repo.all(), isEmpty);
    expect(await db.select(db.pendingAttachments).get(), isEmpty);
    expect(
      Directory('${rig.dir.path}/outbox/${item.commandId}').existsSync(),
      isFalse,
    );
  });

  test('watchFor emits on every change', () async {
    final emissions = <int>[];
    final sub = rig.repo
        .watchFor('o1', 'u1')
        .listen((l) => emissions.add(l.length));
    await Future<void>.delayed(const Duration(milliseconds: 20));
    final item = await rig.enqueue();
    await Future<void>.delayed(const Duration(milliseconds: 20));
    await rig.repo.delete(item.commandId);
    await Future<void>.delayed(const Duration(milliseconds: 20));
    await sub.cancel();
    expect(emissions, [0, 1, 0]);
  });
}
