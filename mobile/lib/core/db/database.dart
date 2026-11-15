import 'package:drift/drift.dart';
import 'package:drift_flutter/drift_flutter.dart';

import 'tables.dart';

part 'database.g.dart';

/// Local SQLite store (Drift).
///
/// Migration strategy: bump [schemaVersion], add a branch in `onUpgrade`
/// (use `m.createTable`, `m.addColumn`), and never edit shipped migrations.
/// `beforeOpen` enables foreign keys. M2 implements the offline logic on
/// `pendingCommands` / `pendingAttachments` / `cachedJobs`.
@DriftDatabase(
  tables: [SessionTable, CachedJobs, PendingCommands, PendingAttachments],
)
class AppDatabase extends _$AppDatabase {
  AppDatabase(super.e);

  /// Production database: file `fixflow_tech.sqlite` in the app data dir.
  factory AppDatabase.open() =>
      AppDatabase(driftDatabase(name: 'fixflow_tech'));

  @override
  int get schemaVersion => 1;

  @override
  MigrationStrategy get migration => MigrationStrategy(
    onCreate: (m) => m.createAll(),
    onUpgrade: (m, from, to) async {
      // Example for the future:
      // if (from < 2) await m.addColumn(cachedJobs, cachedJobs.someColumn);
    },
    beforeOpen: (details) async {
      await customStatement('PRAGMA foreign_keys = ON');
    },
  );

  /// Removes everything that belongs to a signed-in user's read cache.
  /// Deliberately keeps `pending_commands` / `pending_attachments`: queued
  /// offline work must survive sign-out / session expiry (M2).
  Future<void> clearReadCache() async {
    await delete(cachedJobs).go();
    await delete(sessionTable).go();
  }
}
