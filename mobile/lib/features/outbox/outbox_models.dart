import 'dart:convert';

/// Command lifecycle (`pending_commands.status`).
enum OutboxStatus {
  pending,
  syncing,
  conflict,
  failed;

  String get db => name.toUpperCase();

  static OutboxStatus parse(String s) => switch (s) {
    'SYNCING' => syncing,
    'CONFLICT' => conflict,
    'FAILED' => failed,
    _ => pending,
  };
}

/// Machine-readable reasons stored in `pending_commands.error_code`.
class OutboxError {
  static const reassigned = 'reassigned_or_no_access';
  static const closed = 'request_closed';
  static const invalidState = 'invalid_state';
  static const idempotencyReused = 'idempotency_key_reused';
  static const photoRejected = 'photo_rejected';
  static const photoMissing = 'photo_missing';
  static const noteRejected = 'note_rejected';
  static const other = 'rejected';
}

/// One queued photo.
class OutboxPhoto {
  const OutboxPhoto({
    required this.id,
    required this.position,
    required this.localPath,
    required this.mimeType,
    required this.sizeBytes,
    required this.uploaded,
    this.uploadedFileId,
  });
  final int id;
  final int position;
  final String localPath;
  final String mimeType;
  final int sizeBytes;
  final bool uploaded;
  final String? uploadedFileId;
}

/// A queued work note with its photos (UI + sync model).
class OutboxItem {
  const OutboxItem({
    required this.commandId,
    required this.orgId,
    required this.userId,
    required this.requestId,
    required this.requestLabel,
    required this.body,
    required this.visibility,
    required this.status,
    required this.attempts,
    required this.createdAt,
    required this.photos,
    this.lastError,
    this.errorCode,
    this.nextAttemptAt,
  });

  final String commandId;
  final String orgId;
  final String userId;
  final String requestId;

  /// Display id/title captured at enqueue time (e.g. "REQ-7"), for the Outbox list.
  final String requestLabel;
  final String body;
  final String visibility;
  final OutboxStatus status;
  final int attempts;
  final DateTime createdAt;
  final DateTime? nextAttemptAt;
  final String? lastError;
  final String? errorCode;
  final List<OutboxPhoto> photos;

  bool get isConflict => status == OutboxStatus.conflict;

  /// Retrying a conflict is only meaningful when the cause may have changed.
  bool get retryMeaningful =>
      status != OutboxStatus.conflict ||
      (errorCode != OutboxError.idempotencyReused &&
          errorCode != OutboxError.photoMissing);
}

String encodePayload({
  required String body,
  required String visibility,
  required String label,
}) => jsonEncode({'body': body, 'visibility': visibility, 'label': label});

({String body, String visibility, String label}) decodePayload(String json) {
  final m = (jsonDecode(json) as Map).cast<String, dynamic>();
  return (
    body: (m['body'] ?? '') as String,
    visibility: (m['visibility'] ?? 'PUBLIC') as String,
    label: (m['label'] ?? '') as String,
  );
}
