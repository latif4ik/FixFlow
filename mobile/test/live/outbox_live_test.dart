@Tags(['live'])
library;

import 'dart:io';

import 'package:drift/drift.dart' show Value;
import 'package:drift/native.dart';
import 'package:fixflow_tech/core/api/api_client.dart';
import 'package:fixflow_tech/core/auth/auth_repository.dart';
import 'package:fixflow_tech/core/db/database.dart';
import 'package:fixflow_tech/features/jobs/caching_jobs_repository.dart';
import 'package:fixflow_tech/features/jobs/job_models.dart';
import 'package:fixflow_tech/features/jobs/jobs_repository.dart';
import 'package:fixflow_tech/features/outbox/outbox_models.dart';
import 'package:fixflow_tech/features/outbox/outbox_repository.dart';
import 'package:fixflow_tech/features/outbox/sync_engine.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:uuid/uuid.dart';

import '../support/outbox_support.dart' show tinyPng;

/// E2E-04 against the real backend (host side, no emulator):
///   LIVE_API_URL=http://localhost:8000 flutter test test/live
/// Writes demo data; reset afterwards with `reset-demo`.
final liveUrl = Platform.environment['LIVE_API_URL'];

void main() {
  test(
    'offline note + photo is delivered exactly once, even on duplicate '
    'delivery of the same command id',
    () async {
      String? token;
      String orgId = '';
      final api = ApiClient(
        ApiClient.buildDio(
          baseUrl: liveUrl!,
          authContext: () => (token: token, orgId: orgId),
        ),
      );
      final login = await AuthRepository(api)
          .login('technician1@northwind.demo', 'demo1234');
      token = login.token;
      orgId = login.memberships
          .firstWhere((m) => m.isTechnician)
          .organization
          .id;

      final db = AppDatabase(NativeDatabase.memory());
      addTearDown(db.close);
      final caching = CachingJobsRepository(
        ApiJobsRepository(api),
        db,
        () => orgId,
      );

      // Pick an ACTIVE assignment whose request is not closed/canceled
      // (listing it also fills the offline cache, which enqueue requires).
      AssignmentItem? job;
      for (final scope in [AssignmentScope.active, AssignmentScope.upcoming]) {
        final page = await caching.listAssignments(scope: scope);
        for (final i in page.items) {
          if (i.assignmentStatus == 'ACTIVE' &&
              i.status != 'CLOSED' &&
              i.status != 'CANCELED') {
            job ??= i;
          }
        }
      }
      expect(job, isNotNull, reason: 'demo technician has no usable job');
      final requestId = job!.requestId;

      final dir = Directory.systemTemp.createTempSync('ff_live_');
      addTearDown(() => dir.deleteSync(recursive: true));
      final repo = OutboxRepository(db, () async => dir);
      final engine = OutboxSyncEngine(
        repo: repo,
        api: api,
        canSync: () => true,
        userId: () => login.user.id,
        orgId: () => orgId,
      );

      final body = 'M2 live test ${const Uuid().v4()}';
      final png = File('${dir.path}/evidence.png')..writeAsBytesSync(tinyPng);
      final item = await repo.enqueueNote(
        orgId: orgId,
        userId: login.user.id,
        requestId: requestId,
        body: body,
        images: [PickedImage(path: png.path, name: 'evidence.png')],
      );

      final first = await engine.runOnce();
      expect(first.outcome, SyncOutcome.completed);
      expect(first.synced, 1, reason: await _describe(repo));
      expect(await repo.all(), isEmpty);

      // Duplicate delivery: the same command id (+ same photo index) again,
      // as after a lost response / double replay.
      final copy = File('${dir.path}/again.png')..writeAsBytesSync(tinyPng);
      final now = DateTime.now().toUtc();
      await db
          .into(db.pendingCommands)
          .insert(
            PendingCommandsCompanion.insert(
              clientCommandId: item.commandId,
              orgId: orgId,
              requestId: requestId,
              type: 'NOTE',
              payloadJson: encodePayload(
                body: body,
                visibility: 'PUBLIC',
                label: item.requestLabel,
              ),
              userId: Value(login.user.id),
              createdAt: now,
              updatedAt: now,
            ),
          );
      await db
          .into(db.pendingAttachments)
          .insert(
            PendingAttachmentsCompanion.insert(
              clientCommandId: item.commandId,
              position: 0,
              localPath: copy.path,
              mimeType: 'image/png',
              originalFilename: 'evidence.png',
              sizeBytes: tinyPng.length,
            ),
          );
      final second = await engine.runOnce();
      expect(second.synced, 1, reason: await _describe(repo));
      expect(await repo.all(), isEmpty);

      final detail = await api.getJson('/requests/$requestId');
      final notes = [
        for (final n in (detail['notes'] as List))
          if ((n as Map)['body'] == body) n.cast<String, dynamic>(),
      ];
      expect(notes, hasLength(1), reason: 'exactly ONE server note');
      final attachments = notes.single['attachments'] as List;
      expect(attachments, hasLength(1), reason: 'exactly ONE attachment');
      final files = [
        for (final f in (detail['files'] as List? ?? const []))
          if ((f as Map)['note_id'] == notes.single['id']) f,
      ];
      expect(files, hasLength(1));
      // ignore: avoid_print
      print(
        'LIVE OK request=$requestId note=${notes.single['id']} '
        'file=${(attachments.single as Map)['id']}',
      );
    },
    skip: liveUrl == null || liveUrl!.isEmpty
        ? 'set LIVE_API_URL to run against a real backend'
        : false,
  );
}

Future<String> _describe(OutboxRepository repo) async => [
  for (final i in await repo.all())
    '${i.status.name} ${i.lastError ?? ''} ${i.errorCode ?? ''}',
].join('; ');
