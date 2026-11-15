import 'dart:convert';

import 'package:drift/drift.dart';

import '../db/database.dart';
import 'models.dart';

/// Persists NON-secret session info in the Drift `session` table.
class SessionStore {
  SessionStore(this._db);
  final AppDatabase _db;

  Future<void> save({
    required UserProfile user,
    required List<Membership> memberships,
    required String? selectedOrgId,
    DateTime? expiresAt,
  }) async {
    await _db
        .into(_db.sessionTable)
        .insertOnConflictUpdate(
          SessionTableCompanion.insert(
            id: const Value(1),
            userId: user.id,
            email: user.email,
            fullName: user.fullName,
            membershipsJson: jsonEncode([
              for (final m in memberships) m.toJson(),
            ]),
            selectedOrgId: Value(selectedOrgId),
            expiresAt: Value(expiresAt),
            updatedAt: DateTime.now().toUtc(),
          ),
        );
  }

  Future<
    ({
      UserProfile user,
      List<Membership> memberships,
      String? selectedOrgId,
      DateTime? expiresAt,
    })?
  >
  load() async {
    final row = await (_db.select(
      _db.sessionTable,
    )..where((t) => t.id.equals(1))).getSingleOrNull();
    if (row == null) return null;
    final list = (jsonDecode(row.membershipsJson) as List)
        .map((e) => Membership.fromJson((e as Map).cast<String, dynamic>()))
        .toList();
    return (
      user: UserProfile(
        id: row.userId,
        email: row.email,
        fullName: row.fullName,
      ),
      memberships: list,
      selectedOrgId: row.selectedOrgId,
      expiresAt: row.expiresAt,
    );
  }

  Future<void> updateSelectedOrg(String? orgId) async {
    await (_db.update(_db.sessionTable)..where((t) => t.id.equals(1))).write(
      SessionTableCompanion(selectedOrgId: Value(orgId)),
    );
  }

  Future<void> clear() => _db.delete(_db.sessionTable).go();
}
