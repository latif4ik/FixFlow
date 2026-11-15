import 'dart:convert';

import 'package:drift/drift.dart';

import '../../core/api/api_exception.dart';
import '../../core/db/database.dart';
import 'job_models.dart';
import 'jobs_repository.dart';

/// Offline-first read access (MOB-04): every successful fetch of the
/// technician's OWN assigned jobs is written to `cached_jobs` (scoped by org);
/// on a [NetworkException] the cache is served and flagged `stale`.
class CachingJobsRepository implements JobsRepository {
  CachingJobsRepository(
    this._inner,
    this._db,
    this._orgId, {
    DateTime Function()? clock,
  }) : _now = clock ?? DateTime.now;

  /// Most history rows kept per organization (oldest evicted first).
  static const historyCap = 50;

  final JobsRepository _inner;
  final AppDatabase _db;
  final String? Function() _orgId;
  final DateTime Function() _now;

  @override
  Future<AssignmentPage> listAssignments({
    required AssignmentScope scope,
    int page = 1,
    int pageSize = 20,
  }) async {
    final org = _orgId();
    try {
      final result = await _inner.listAssignments(
        scope: scope,
        page: page,
        pageSize: pageSize,
      );
      if (org != null) {
        await _storeItems(org, scope, page, result);
      }
      return result;
    } on NetworkException {
      if (org == null) rethrow;
      final cached = await _readItems(org, scope, page, pageSize);
      if (cached == null) rethrow;
      return cached;
    }
  }

  @override
  Future<JobDetail> getJob(String requestId) async {
    final org = _orgId();
    try {
      final job = await _inner.getJob(requestId);
      if (org != null) await _storeDetail(org, requestId, job);
      return job;
    } on NetworkException {
      if (org == null) rethrow;
      final row = await _row(org, requestId);
      if (row?.detailJson == null) rethrow;
      final job = JobDetail.fromJson(
        (jsonDecode(row!.detailJson!) as Map).cast<String, dynamic>(),
      );
      return job.asStale(row.fetchedAt);
    } on ApiException catch (e) {
      // No longer visible to this technician: do not keep serving it.
      if (org != null && (e.isNotFound || e.isForbidden)) {
        await (_db.delete(_db.cachedJobs)..where(
              (t) => t.orgId.equals(org) & t.requestId.equals(requestId),
            ))
            .go();
      }
      rethrow;
    }
  }

  Future<CachedJobRow?> _row(String org, String requestId) =>
      (_db.select(_db.cachedJobs)
            ..where((t) => t.orgId.equals(org) & t.requestId.equals(requestId)))
          .getSingleOrNull();

  Future<void> _storeItems(
    String org,
    AssignmentScope scope,
    int page,
    AssignmentPage result,
  ) async {
    final now = _now().toUtc();
    await _db.transaction(() async {
      if (page == 1 && result.items.length >= result.total) {
        // Complete listing: forget rows of this scope that are gone. A job
        // that merely moved to another scope (ACCEPTED -> IN_PROGRESS) keeps
        // its cached DETAIL (so it still opens offline); only its list entry
        // is dropped. A job that is really gone is evicted by the 403/404 on
        // its next online detail fetch.
        final keep = [for (final i in result.items) i.requestId];
        Expression<bool> gone($CachedJobsTable t) =>
            t.orgId.equals(org) &
            t.scope.equals(scope.name) &
            t.requestId.isNotIn(keep);
        await (_db.delete(
          _db.cachedJobs,
        )..where((t) => gone(t) & t.detailJson.isNull())).go();
        await (_db.update(_db.cachedJobs)
              ..where((t) => gone(t) & t.detailJson.isNotNull()))
            .write(const CachedJobsCompanion(itemJson: Value(null)));
      }
      for (final item in result.items) {
        final raw = item.raw;
        if (raw == null) continue;
        await _db
            .into(_db.cachedJobs)
            .insert(
              CachedJobsCompanion.insert(
                orgId: org,
                requestId: item.requestId,
                assignmentId: Value(item.assignmentId),
                scope: Value(scope.name),
                itemJson: Value(jsonEncode(raw)),
                fetchedAt: now,
              ),
              onConflict: DoUpdate(
                (_) => CachedJobsCompanion(
                  assignmentId: Value(item.assignmentId),
                  scope: Value(scope.name),
                  itemJson: Value(jsonEncode(raw)),
                  fetchedAt: Value(now),
                ),
              ),
            );
      }
      await _evictHistory(org);
    });
  }

  Future<void> _storeDetail(String org, String requestId, JobDetail job) async {
    final raw = job.raw;
    if (raw == null) return;
    final now = _now().toUtc();
    await _db
        .into(_db.cachedJobs)
        .insert(
          CachedJobsCompanion.insert(
            orgId: org,
            requestId: requestId,
            detailJson: Value(jsonEncode(raw)),
            fetchedAt: now,
          ),
          onConflict: DoUpdate(
            (_) => CachedJobsCompanion(
              detailJson: Value(jsonEncode(raw)),
              fetchedAt: Value(now),
            ),
          ),
        );
  }

  Future<void> _evictHistory(String org) async {
    final rows =
        await (_db.select(_db.cachedJobs)
              ..where((t) => t.orgId.equals(org) & t.scope.equals('history'))
              ..orderBy([(t) => OrderingTerm.desc(t.fetchedAt)]))
            .get();
    if (rows.length <= historyCap) return;
    for (final r in rows.skip(historyCap)) {
      await (_db.delete(_db.cachedJobs)..where(
            (t) => t.orgId.equals(org) & t.requestId.equals(r.requestId),
          ))
          .go();
    }
  }

  /// Returns null when nothing at all is cached for this org (the caller then
  /// surfaces the original offline error).
  Future<AssignmentPage?> _readItems(
    String org,
    AssignmentScope scope,
    int page,
    int pageSize,
  ) async {
    final all = await (_db.select(
      _db.cachedJobs,
    )..where((t) => t.orgId.equals(org))).get();
    if (all.isEmpty) return null;
    final syncedAt = all
        .map((r) => r.fetchedAt)
        .reduce((a, b) => a.isAfter(b) ? a : b);
    final items = <AssignmentItem>[];
    for (final r in all) {
      if (r.scope != scope.name || r.itemJson == null) continue;
      items.add(
        AssignmentItem.fromJson(
          (jsonDecode(r.itemJson!) as Map).cast<String, dynamic>(),
        ),
      );
    }
    items.sort((a, b) {
      final x = a.appointment?.start;
      final y = b.appointment?.start;
      if (x == null && y == null) return 0;
      if (x == null) return 1;
      if (y == null) return -1;
      return scope == AssignmentScope.history ? y.compareTo(x) : x.compareTo(y);
    });
    return AssignmentPage(
      // The whole cached scope is returned as page 1.
      items: page == 1 ? items : const [],
      total: items.length,
      page: page,
      pageSize: pageSize,
      stale: true,
      syncedAt: syncedAt.toLocal(),
    );
  }
}
