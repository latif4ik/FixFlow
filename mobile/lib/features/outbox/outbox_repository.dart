import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math';

import 'package:drift/drift.dart';
import 'package:path/path.dart' as p;
import 'package:uuid/uuid.dart';

import '../../core/db/database.dart';
import 'outbox_models.dart';

/// Thrown when a note cannot be queued; [message] is user-facing.
class OutboxRejected implements Exception {
  const OutboxRejected(this.message);
  final String message;
  @override
  String toString() => 'OutboxRejected: $message';
}

/// An image chosen on the device.
class PickedImage {
  const PickedImage({required this.path, this.name});
  final String path;
  final String? name;
}

/// Sniffs jpeg/png/webp from magic bytes; null when unsupported.
({String mime, String ext})? sniffImage(List<int> head) {
  bool at(int i, List<int> sig) {
    if (head.length < i + sig.length) return false;
    for (var k = 0; k < sig.length; k++) {
      if (head[i + k] != sig[k]) return false;
    }
    return true;
  }

  if (at(0, [0xFF, 0xD8, 0xFF])) return (mime: 'image/jpeg', ext: 'jpg');
  if (at(0, [0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A])) {
    return (mime: 'image/png', ext: 'png');
  }
  if (at(0, [0x52, 0x49, 0x46, 0x46]) && at(8, [0x57, 0x45, 0x42, 0x50])) {
    return (mime: 'image/webp', ext: 'webp');
  }
  return null;
}

/// Persistent outbox over `pending_commands` / `pending_attachments`.
class OutboxRepository {
  OutboxRepository(
    this._db,
    this._rootDir, {
    DateTime Function()? clock,
    String Function()? newId,
  }) : _now = clock ?? DateTime.now,
       _newId = newId ?? (() => const Uuid().v4());

  static const maxPhotos = 5;
  static const maxPhotoBytes = 10 * 1024 * 1024;
  static const maxBodyLength = 2000;

  final AppDatabase _db;

  /// Resolves the app documents directory (injected; tests use a temp dir).
  final Future<Directory> Function() _rootDir;
  final DateTime Function() _now;
  final String Function() _newId;

  /// Queues a NOTE for a job that is in the offline cache with an ACTIVE
  /// assignment. Everything is written in ONE transaction (files are copied
  /// first and removed again if the transaction fails).
  Future<OutboxItem> enqueueNote({
    required String orgId,
    required String userId,
    required String requestId,
    required String body,
    String visibility = 'PUBLIC',
    List<PickedImage> images = const [],
  }) async {
    final text = body.trim();
    if (text.isEmpty) throw const OutboxRejected('Write a note first.');
    if (text.length > maxBodyLength) {
      throw const OutboxRejected(
        'The note is too long (maximum $maxBodyLength characters).',
      );
    }
    if (images.length > maxPhotos) {
      throw const OutboxRejected('You can attach up to $maxPhotos photos.');
    }
    if (visibility != 'PUBLIC' && visibility != 'INTERNAL') {
      throw const OutboxRejected('Unknown note visibility.');
    }
    final job =
        await (_db.select(_db.cachedJobs)..where(
              (t) => t.orgId.equals(orgId) & t.requestId.equals(requestId),
            ))
            .getSingleOrNull();
    final item = job?.itemJson;
    if (job == null || item == null) {
      throw const OutboxRejected(
        'This job is not available offline, so a note cannot be queued.',
      );
    }
    final json = _decode(item);
    final request = (json['request'] as Map?) ?? const {};
    final status = (request['status'] ?? '') as String;
    if (json['assignment_status'] != 'ACTIVE') {
      throw const OutboxRejected('You are no longer assigned to this job.');
    }
    if (status == 'CLOSED' || status == 'CANCELED') {
      throw const OutboxRejected('This request is closed.');
    }
    final label = (request['display_id'] ?? '') as String;

    // Validate every image BEFORE touching the disk.
    final checked = <({PickedImage src, String mime, String ext, int size})>[];
    for (final img in images) {
      final file = File(img.path);
      final name = img.name ?? p.basename(img.path);
      if (!await file.exists()) {
        throw OutboxRejected('Photo "$name" could not be read.');
      }
      final size = await file.length();
      if (size > maxPhotoBytes) {
        throw OutboxRejected('Photo "$name" is larger than 10 MB.');
      }
      if (size == 0) throw OutboxRejected('Photo "$name" is empty.');
      final raf = await file.open();
      final head = await raf.read(16);
      await raf.close();
      final sniffed = sniffImage(head);
      if (sniffed == null) {
        throw OutboxRejected('Photo "$name" is not a JPEG, PNG or WebP image.');
      }
      checked.add((src: img, mime: sniffed.mime, ext: sniffed.ext, size: size));
    }

    final id = _newId();
    final now = _now().toUtc();
    final dir = Directory(p.join((await _rootDir()).path, 'outbox', id));
    try {
      final copies = <String>[];
      if (checked.isNotEmpty) {
        await dir.create(recursive: true);
        for (var i = 0; i < checked.length; i++) {
          final dest = p.join(dir.path, '$i.${checked[i].ext}');
          await File(checked[i].src.path).copy(dest);
          copies.add(dest);
        }
      }
      await _db.transaction(() async {
        await _db
            .into(_db.pendingCommands)
            .insert(
              PendingCommandsCompanion.insert(
                clientCommandId: id,
                orgId: orgId,
                requestId: requestId,
                type: 'NOTE',
                payloadJson: encodePayload(
                  body: text,
                  visibility: visibility,
                  label: label,
                ),
                userId: Value(userId),
                createdAt: now,
                updatedAt: now,
              ),
            );
        for (var i = 0; i < checked.length; i++) {
          await _db
              .into(_db.pendingAttachments)
              .insert(
                PendingAttachmentsCompanion.insert(
                  clientCommandId: id,
                  position: i,
                  localPath: copies[i],
                  mimeType: checked[i].mime,
                  originalFilename:
                      '${_stem(checked[i].src.name ?? checked[i].src.path)}.${checked[i].ext}',
                  sizeBytes: checked[i].size,
                ),
              );
        }
      });
    } catch (_) {
      if (await dir.exists()) await dir.delete(recursive: true);
      rethrow;
    }
    _notify();
    return (await getItem(id))!;
  }

  static String _stem(String path) {
    final b = p.basenameWithoutExtension(path);
    return b.isEmpty ? 'photo' : b;
  }

  static Map<String, dynamic> _decode(String s) =>
      (jsonDecode(s) as Map).cast<String, dynamic>();

  // ---- reads ---------------------------------------------------------

  Future<OutboxItem?> getItem(String commandId) async {
    final row = await (_db.select(
      _db.pendingCommands,
    )..where((t) => t.clientCommandId.equals(commandId))).getSingleOrNull();
    if (row == null) return null;
    return (await _assemble([row])).single;
  }

  /// All commands (any user/org), oldest first.
  Future<List<OutboxItem>> all() async => _assemble(
    await (_db.select(
      _db.pendingCommands,
    )..orderBy([(t) => OrderingTerm.asc(t.id)])).get(),
  );

  /// PENDING commands of this user in this org, FIFO (queue order).
  Future<List<OutboxItem>> pendingFor(String orgId, String userId) async =>
      _assemble(
        await (_db.select(_db.pendingCommands)
              ..where(
                (t) =>
                    t.orgId.equals(orgId) &
                    t.userId.equals(userId) &
                    t.status.equals(OutboxStatus.pending.db),
              )
              ..orderBy([(t) => OrderingTerm.asc(t.id)]))
            .get(),
      );

  /// Live list for [orgId] + [userId] (oldest first). Implemented with an
  /// in-process change signal (all writes go through this repository) instead
  /// of Drift query streams.
  Stream<List<OutboxItem>> watchFor(String orgId, String userId) => _watch(
    () async => _assemble(
      await (_db.select(_db.pendingCommands)
            ..where((t) => t.orgId.equals(orgId) & t.userId.equals(userId))
            ..orderBy([(t) => OrderingTerm.asc(t.id)]))
          .get(),
    ),
  );

  /// Commands owned by OTHER users (any org); their payload is never shown.
  Stream<int> watchOtherUsersCount(String userId) => _watch(() async {
    final rows = await (_db.select(
      _db.pendingCommands,
    )..where((t) => t.userId.equals(userId).not())).get();
    return rows.length;
  });

  final _changes = StreamController<void>.broadcast(sync: true);
  void _notify() {
    if (!_changes.isClosed) _changes.add(null);
  }

  Stream<T> _watch<T>(Future<T> Function() query) {
    late StreamController<T> controller;
    StreamSubscription<void>? sub;
    var version = 0;
    Future<void> emit() async {
      final mine = ++version;
      try {
        final value = await query();
        if (!controller.isClosed && mine == version) controller.add(value);
      } catch (e, st) {
        if (!controller.isClosed) controller.addError(e, st);
      }
    }

    controller = StreamController<T>(
      onListen: () {
        sub = _changes.stream.listen((_) => emit());
        emit();
      },
      onCancel: () => sub?.cancel(),
    );
    return controller.stream;
  }

  Future<List<OutboxItem>> _assemble(List<PendingCommandRow> rows) async {
    if (rows.isEmpty) return const [];
    final atts =
        await (_db.select(_db.pendingAttachments)
              ..where(
                (t) => t.clientCommandId.isIn([
                  for (final r in rows) r.clientCommandId,
                ]),
              )
              ..orderBy([(t) => OrderingTerm.asc(t.position)]))
            .get();
    return [
      for (final r in rows)
        () {
          final payload = decodePayload(r.payloadJson);
          return OutboxItem(
            commandId: r.clientCommandId,
            orgId: r.orgId,
            userId: r.userId,
            requestId: r.requestId,
            requestLabel: payload.label,
            body: payload.body,
            visibility: payload.visibility,
            status: OutboxStatus.parse(r.status),
            attempts: r.attempts,
            createdAt: r.createdAt.toLocal(),
            nextAttemptAt: r.nextAttemptAt?.toLocal(),
            lastError: r.lastError,
            errorCode: r.errorCode,
            photos: [
              for (final a in atts.where(
                (a) => a.clientCommandId == r.clientCommandId,
              ))
                OutboxPhoto(
                  id: a.id,
                  position: a.position,
                  localPath: a.localPath,
                  mimeType: a.mimeType,
                  sizeBytes: a.sizeBytes,
                  uploaded: a.uploadedFileId != null,
                  uploadedFileId: a.uploadedFileId,
                ),
            ],
          );
        }(),
    ];
  }

  // ---- state changes -------------------------------------------------

  /// Crash recovery: anything left SYNCING by a killed process is PENDING again.
  Future<int> resetSyncing() =>
      (_db.update(
        _db.pendingCommands,
      )..where((t) => t.status.equals(OutboxStatus.syncing.db))).write(
        PendingCommandsCompanion(
          status: Value(OutboxStatus.pending.db),
          updatedAt: Value(_now().toUtc()),
        ),
      );

  Future<void> _setStatus(
    String id,
    PendingCommandsCompanion Function(DateTime now) build,
  ) async {
    await (_db.update(
      _db.pendingCommands,
    )..where((t) => t.clientCommandId.equals(id))).write(build(_now().toUtc()));
    _notify();
  }

  Future<void> markSyncing(String id) => _setStatus(
    id,
    (now) => PendingCommandsCompanion(
      status: Value(OutboxStatus.syncing.db),
      updatedAt: Value(now),
    ),
  );

  /// Retryable failure: back to PENDING with attempts+1 and a backoff time.
  Future<void> markRetry(
    String id,
    String error,
    DateTime nextAttemptAt,
  ) async {
    final row = await (_db.select(
      _db.pendingCommands,
    )..where((t) => t.clientCommandId.equals(id))).getSingleOrNull();
    if (row == null) return;
    await _setStatus(
      id,
      (now) => PendingCommandsCompanion(
        status: Value(OutboxStatus.pending.db),
        attempts: Value(row.attempts + 1),
        lastError: Value(error),
        errorCode: const Value(null),
        nextAttemptAt: Value(nextAttemptAt.toUtc()),
        updatedAt: Value(now),
      ),
    );
  }

  /// Back to PENDING without counting an attempt (e.g. 401: queue kept).
  Future<void> markPending(String id) => _setStatus(
    id,
    (now) => PendingCommandsCompanion(
      status: Value(OutboxStatus.pending.db),
      updatedAt: Value(now),
    ),
  );

  Future<void> markConflict(String id, String code, String reason) async {
    final row = await (_db.select(
      _db.pendingCommands,
    )..where((t) => t.clientCommandId.equals(id))).getSingleOrNull();
    if (row == null) return;
    await _setStatus(
      id,
      (now) => PendingCommandsCompanion(
        status: Value(OutboxStatus.conflict.db),
        attempts: Value(row.attempts + 1),
        lastError: Value(reason),
        errorCode: Value(code),
        nextAttemptAt: const Value(null),
        updatedAt: Value(now),
      ),
    );
  }

  /// User pressed Retry: back to PENDING, due immediately. Photos already
  /// uploaded stay uploaded; rejected ones are retried.
  Future<void> retry(String id) => _setStatus(
    id,
    (now) => PendingCommandsCompanion(
      status: Value(OutboxStatus.pending.db),
      nextAttemptAt: const Value(null),
      errorCode: const Value(null),
      updatedAt: Value(now),
    ),
  );

  Future<void> markPhotoUploaded(int attachmentId, String fileId) =>
      (_db.update(
        _db.pendingAttachments,
      )..where((t) => t.id.equals(attachmentId))).write(
        PendingAttachmentsCompanion(
          status: const Value('UPLOADED'),
          uploadedFileId: Value(fileId),
        ),
      );

  /// Removes the command, its attachment rows and its local files.
  Future<void> delete(String commandId) async {
    await _db.transaction(() async {
      await (_db.delete(
        _db.pendingAttachments,
      )..where((t) => t.clientCommandId.equals(commandId))).go();
      await (_db.delete(
        _db.pendingCommands,
      )..where((t) => t.clientCommandId.equals(commandId))).go();
    });
    _notify();
    final dir = Directory(p.join((await _rootDir()).path, 'outbox', commandId));
    if (await dir.exists()) await dir.delete(recursive: true);
  }

  /// Discards every command owned by users other than [userId].
  Future<void> deleteOtherUsers(String userId) async {
    final rows = await (_db.select(
      _db.pendingCommands,
    )..where((t) => t.userId.equals(userId).not())).get();
    for (final r in rows) {
      await delete(r.clientCommandId);
    }
  }

  /// Exponential backoff with jitter: 5s, 10s, 20s ... capped at 5 minutes.
  static Duration backoff(int attempts, [Random? random]) {
    final base = min(300, 5 * pow(2, max(0, attempts - 1)).toInt());
    final jitter = 0.8 + (random ?? Random()).nextDouble() * 0.2; // 0.8..1.0
    return Duration(milliseconds: (base * 1000 * jitter).round());
  }
}
