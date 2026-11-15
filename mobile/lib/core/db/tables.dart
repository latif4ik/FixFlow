import 'package:drift/drift.dart';

/// Single-row table (id = 1): NON-secret session info. The bearer token lives
/// in flutter_secure_storage, never here.
@DataClassName('SessionRow')
class SessionTable extends Table {
  @override
  String get tableName => 'session';

  IntColumn get id => integer()();
  TextColumn get userId => text()();
  TextColumn get email => text()();
  TextColumn get fullName => text()();
  // JSON array of memberships exactly as returned by /auth/login.
  TextColumn get membershipsJson => text()();
  TextColumn get selectedOrgId => text().nullable()();
  DateTimeColumn get expiresAt => dateTime().nullable()();
  DateTimeColumn get updatedAt => dateTime()();

  @override
  Set<Column> get primaryKey => {id};
}

/// Offline cache of assigned jobs, scoped by organization (AUTH-04: rows of
/// one org must never be shown under another).
@DataClassName('CachedJobRow')
class CachedJobs extends Table {
  TextColumn get orgId => text()();
  TextColumn get requestId => text()();
  TextColumn get assignmentId => text().nullable()();
  // upcoming | active | history (last scope the job was listed in)
  TextColumn get scope => text().nullable()();
  // /me/assignments item JSON (list card + allowed_actions).
  TextColumn get itemJson => text().nullable()();
  // /requests/{id} JSON, when the detail has been opened/prefetched.
  TextColumn get detailJson => text().nullable()();
  DateTimeColumn get fetchedAt => dateTime()();

  @override
  Set<Column> get primaryKey => {orgId, requestId};
}

/// Outbox of offline writes (M2). Replayed in `id` order per request.
/// `status`: PENDING | SYNCING | CONFLICT | FAILED.
@DataClassName('PendingCommandRow')
class PendingCommands extends Table {
  IntColumn get id => integer().autoIncrement()();
  // UUID generated on the device; sent as the idempotency key.
  TextColumn get clientCommandId => text().unique()();
  TextColumn get orgId => text()();
  TextColumn get requestId => text()();
  // NOTE (more types later)
  TextColumn get type => text()();
  TextColumn get payloadJson => text()();
  TextColumn get status => text().withDefault(const Constant('PENDING'))();
  IntColumn get attempts => integer().withDefault(const Constant(0))();
  TextColumn get lastError => text().nullable()();
  DateTimeColumn get nextAttemptAt => dateTime().nullable()();
  // Schema v2: owner of the command (a different signed-in user must never
  // replay it) and a machine-readable reason for CONFLICT/FAILED.
  TextColumn get userId => text().withDefault(const Constant(''))();
  TextColumn get errorCode => text().nullable()();
  DateTimeColumn get createdAt => dateTime()();
  DateTimeColumn get updatedAt => dateTime()();
}

/// Images attached to a pending command; files copied into the app documents
/// directory. Upload key = (clientCommandId, position).
/// `status`: PENDING | UPLOADED | FAILED.
@DataClassName('PendingAttachmentRow')
class PendingAttachments extends Table {
  IntColumn get id => integer().autoIncrement()();
  TextColumn get clientCommandId =>
      text().references(PendingCommands, #clientCommandId)();
  IntColumn get position => integer()();
  TextColumn get localPath => text()();
  TextColumn get mimeType => text()();
  TextColumn get originalFilename => text()();
  IntColumn get sizeBytes => integer()();
  TextColumn get status => text().withDefault(const Constant('PENDING'))();
  // Server file id once uploaded (so a retry does not re-upload).
  TextColumn get uploadedFileId => text().nullable()();

  @override
  List<Set<Column>> get uniqueKeys => [
    {clientCommandId, position},
  ];
}
