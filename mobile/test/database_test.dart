import 'package:drift/drift.dart' hide isNull;
import 'package:drift/native.dart';
import 'package:fixflow_tech/core/db/database.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  late AppDatabase db;
  setUp(() => db = AppDatabase(NativeDatabase.memory()));
  tearDown(() => db.close());

  test('opens in memory with the full schema', () async {
    final rows = await db
        .customSelect("SELECT name FROM sqlite_master WHERE type = 'table'")
        .get();
    final names = rows.map((r) => r.read<String>('name')).toSet();
    expect(
      names,
      containsAll([
        'session',
        'cached_jobs',
        'pending_commands',
        'pending_attachments',
      ]),
    );
    expect(db.schemaVersion, 2);
  });

  test('cached_jobs is keyed by (org, request)', () async {
    Future<void> put(String org, String req) => db
        .into(db.cachedJobs)
        .insert(
          CachedJobsCompanion.insert(
            orgId: org,
            requestId: req,
            fetchedAt: DateTime.utc(2026),
          ),
        );
    await put('o1', 'r1');
    await put('o2', 'r1'); // same request id, different org is fine
    expect(() => put('o1', 'r1'), throwsA(anything));
    expect(await db.select(db.cachedJobs).get(), hasLength(2));
  });

  test('pending command + attachment round trip; command id unique', () async {
    final now = DateTime.utc(2026);
    await db
        .into(db.pendingCommands)
        .insert(
          PendingCommandsCompanion.insert(
            clientCommandId: 'c1',
            orgId: 'o1',
            requestId: 'r1',
            type: 'ADD_NOTE',
            payloadJson: '{"body":"x"}',
            createdAt: now,
            updatedAt: now,
          ),
        );
    await db
        .into(db.pendingAttachments)
        .insert(
          PendingAttachmentsCompanion.insert(
            clientCommandId: 'c1',
            position: 0,
            localPath: '/data/a.jpg',
            mimeType: 'image/jpeg',
            originalFilename: 'a.jpg',
            sizeBytes: 10,
          ),
        );
    final cmd = await db.select(db.pendingCommands).getSingle();
    expect(cmd.status, 'PENDING');
    expect(cmd.attempts, 0);
    final att = await db.select(db.pendingAttachments).getSingle();
    expect(att.status, 'PENDING');
    expect(att.uploadedFileId, isNull);
    await expectLater(
      db
          .into(db.pendingCommands)
          .insert(
            PendingCommandsCompanion.insert(
              clientCommandId: 'c1',
              orgId: 'o1',
              requestId: 'r1',
              type: 'ADD_NOTE',
              payloadJson: '{}',
              createdAt: now,
              updatedAt: now,
            ),
          ),
      throwsA(anything),
    );
    // foreign key enforced
    await expectLater(
      db
          .into(db.pendingAttachments)
          .insert(
            PendingAttachmentsCompanion.insert(
              clientCommandId: 'missing',
              position: 0,
              localPath: 'p',
              mimeType: 'm',
              originalFilename: 'f',
              sizeBytes: 1,
            ),
          ),
      throwsA(anything),
    );
  });

  test('clearReadCache keeps the offline queue', () async {
    final now = DateTime.utc(2026);
    await db
        .into(db.cachedJobs)
        .insert(
          CachedJobsCompanion.insert(
            orgId: 'o',
            requestId: 'r',
            fetchedAt: now,
          ),
        );
    await db
        .into(db.pendingCommands)
        .insert(
          PendingCommandsCompanion.insert(
            clientCommandId: 'c',
            orgId: 'o',
            requestId: 'r',
            type: 'ADD_NOTE',
            payloadJson: '{}',
            createdAt: now,
            updatedAt: now,
          ),
        );
    await db.clearReadCache();
    expect(await db.select(db.cachedJobs).get(), isEmpty);
    expect(await db.select(db.pendingCommands).get(), hasLength(1));
    expect(const Value(1).present, isTrue);
  });
}
