import 'dart:io';
import 'dart:math';

import 'package:dio/dio.dart';
import 'package:path/path.dart' as p;

import '../../core/api/api_client.dart';
import '../../core/api/api_exception.dart';
import 'outbox_models.dart';
import 'outbox_repository.dart';

enum SyncOutcome {
  /// The run completed (individual items may still be pending/conflicts).
  completed,

  /// Nothing to do: signed out, no org, or the network is unavailable.
  skipped,

  /// The server rejected the session (401): sync stopped, queue kept.
  unauthorized,

  /// Connection failed mid-run: remaining items wait for the next trigger.
  networkDown,
}

class SyncReport {
  const SyncReport(
    this.outcome, {
    this.syncedRequestIds = const {},
    this.synced = 0,
    this.conflicts = 0,
    this.retries = 0,
  });
  final SyncOutcome outcome;
  final Set<String> syncedRequestIds;
  final int synced;
  final int conflicts;
  final int retries;
}

/// (code, user-facing reason) for a server rejection.
({String code, String reason}) describeRejection(
  ApiException e, {
  required bool photo,
}) {
  final text = e.message.trim();
  final lower = '${e.code} $text'.toLowerCase();
  if (e.status == 403 || e.status == 404) {
    return (
      code: OutboxError.reassigned,
      reason:
          'This job was reassigned, or you no longer have access to it. '
          'Your note was not sent and is kept on this device.',
    );
  }
  if (e.status == 409) {
    if (e.code == 'idempotency_key_reused') {
      return (
        code: OutboxError.idempotencyReused,
        reason:
            'The server already has a different note saved under this '
            "note's ID, so this one was not sent. Copy your text, then discard it.",
      );
    }
    if (lower.contains('clos') ||
        lower.contains('cancel') ||
        e.code == 'invalid_transition') {
      return (
        code: OutboxError.closed,
        reason: 'The request is closed or canceled, so notes can no longer be added.',
      );
    }
    return (
      code: OutboxError.invalidState,
      reason:
          'The job changed on the server and the note cannot be added'
          '${text.isEmpty ? '.' : ': $text'}',
    );
  }
  if (photo) {
    return (
      code: OutboxError.photoRejected,
      reason: 'Photo rejected by server: ${text.isEmpty ? e.code : text}',
    );
  }
  return (
    code: OutboxError.noteRejected,
    reason: 'Note rejected by server: ${text.isEmpty ? e.code : text}',
  );
}

bool _retryable(ApiException e) =>
    e.status >= 500 || e.status == 429 || e.status == 408;

/// Replays queued NOTE commands (MOB-06). Pure Dart (no Riverpod) so it is
/// unit-testable and usable from the live test.
///
/// Per command: upload every photo not yet uploaded (file ids are persisted
/// immediately; the server also dedupes on (client_command_id, client_index)),
/// then POST the note with the same `client_command_id` and the collected
/// `attachment_ids`. A 200 replay is a success exactly like a 201.
class OutboxSyncEngine {
  OutboxSyncEngine({
    required this.repo,
    required this.api,
    required this.canSync,
    required this.userId,
    required this.orgId,
    DateTime Function()? clock,
    Random? random,
  }) : _now = clock ?? DateTime.now,
       _random = random ?? Random();

  final OutboxRepository repo;
  final ApiClient api;

  /// False while offline (or the dev "Simulate offline" switch is on): no
  /// request is sent at all.
  final bool Function() canSync;
  final String? Function() userId;
  final String? Function() orgId;
  final DateTime Function() _now;
  final Random _random;

  bool _running = false;
  bool _rerun = false;
  bool get isRunning => _running;

  /// Single-flight: a call while a run is active returns immediately and
  /// schedules one extra pass so freshly queued items are not missed.
  /// [force] ignores backoff timestamps (manual Retry).
  Future<SyncReport> runOnce({bool force = false}) async {
    if (_running) {
      _rerun = true;
      return const SyncReport(SyncOutcome.skipped);
    }
    _running = true;
    var synced = <String>{};
    var syncedCount = 0, conflicts = 0, retries = 0;
    try {
      do {
        _rerun = false;
        final user = userId();
        final org = orgId();
        if (user == null || org == null || !canSync()) {
          return SyncReport(
            SyncOutcome.skipped,
            syncedRequestIds: synced,
            synced: syncedCount,
          );
        }
        final items = await repo.pendingFor(org, user);
        final blocked = <String>{};
        for (final item in items) {
          if (blocked.contains(item.requestId)) continue; // FIFO per request
          if (!force &&
              item.nextAttemptAt != null &&
              item.nextAttemptAt!.isAfter(_now())) {
            blocked.add(item.requestId);
            continue;
          }
          if (userId() != user || orgId() != org || !canSync()) {
            return SyncReport(
              SyncOutcome.skipped,
              syncedRequestIds: synced,
              synced: syncedCount,
              conflicts: conflicts,
              retries: retries,
            );
          }
          final r = await _process(item);
          switch (r) {
            case _Result.synced:
              synced = {...synced, item.requestId};
              syncedCount++;
            case _Result.conflict:
              conflicts++;
            case _Result.retry:
              retries++;
              blocked.add(item.requestId);
            case _Result.networkDown:
              return SyncReport(
                SyncOutcome.networkDown,
                syncedRequestIds: synced,
                synced: syncedCount,
                conflicts: conflicts,
                retries: retries + 1,
              );
            case _Result.unauthorized:
              return SyncReport(
                SyncOutcome.unauthorized,
                syncedRequestIds: synced,
                synced: syncedCount,
                conflicts: conflicts,
                retries: retries,
              );
          }
        }
      } while (_rerun);
      return SyncReport(
        SyncOutcome.completed,
        syncedRequestIds: synced,
        synced: syncedCount,
        conflicts: conflicts,
        retries: retries,
      );
    } finally {
      _running = false;
    }
  }

  Future<_Result> _process(OutboxItem item) async {
    final id = item.commandId;
    await repo.markSyncing(id);
    var uploadingPhoto = false;
    try {
      final fileIds = <String>[];
      for (final photo in item.photos) {
        if (photo.uploadedFileId != null) {
          fileIds.add(photo.uploadedFileId!);
          continue;
        }
        final file = File(photo.localPath);
        if (!await file.exists()) {
          await repo.markConflict(
            id,
            OutboxError.photoMissing,
            'A photo file is missing from this device, so the note cannot '
            'be sent with it. Copy your text, then discard the draft.',
          );
          return _Result.conflict;
        }
        uploadingPhoto = true;
        final form = FormData.fromMap({
          'purpose': 'NOTE',
          'client_command_id': id,
          'client_index': photo.position,
          'file': await MultipartFile.fromFile(
            photo.localPath,
            filename: p.basename(photo.localPath),
            contentType: DioMediaType.parse(photo.mimeType),
          ),
        });
        final json = await api.postForm(
          '/requests/${item.requestId}/files',
          form,
        );
        final fileId = json['id'];
        if (fileId is! String) {
          throw const ApiException(
            status: 502,
            code: 'bad_response',
            message: 'The server did not return a file id.',
          );
        }
        await repo.markPhotoUploaded(photo.id, fileId);
        fileIds.add(fileId);
        uploadingPhoto = false;
      }
      await api.postJson(
        '/requests/${item.requestId}/notes',
        body: {
          'body': item.body,
          'visibility': item.visibility,
          'client_command_id': id,
          'attachment_ids': fileIds,
        },
      );
      await repo.delete(id); // 201 and 200 (replay) both end here
      return _Result.synced;
    } on NetworkException catch (e) {
      await repo.markRetry(id, _networkMessage(e), _next(item.attempts + 1));
      return _Result.networkDown;
    } on ApiException catch (e) {
      if (e.isUnauthorized) {
        await repo.markPending(id);
        return _Result.unauthorized;
      }
      if (_retryable(e)) {
        await repo.markRetry(
          id,
          'Server error (${e.status}); will retry.',
          _next(item.attempts + 1),
        );
        return _Result.retry;
      }
      final photoRejection =
          uploadingPhoto && const {400, 413, 415, 422}.contains(e.status);
      final d = describeRejection(e, photo: photoRejection);
      await repo.markConflict(id, d.code, d.reason);
      return _Result.conflict;
    } catch (e) {
      // Unexpected local failure (I/O ...): keep the item, retry later.
      await repo.markRetry(
        id,
        'Unexpected error; will retry.',
        _next(item.attempts + 1),
      );
      return _Result.retry;
    }
  }

  String _networkMessage(NetworkException e) => e.timedOut
      ? 'The server took too long to respond; will retry.'
      : 'Offline or server unreachable; will retry.';

  DateTime _next(int attempts) =>
      _now().add(OutboxRepository.backoff(attempts, _random));
}

enum _Result { synced, conflict, retry, networkDown, unauthorized }
