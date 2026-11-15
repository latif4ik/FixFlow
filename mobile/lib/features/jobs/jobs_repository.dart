import '../../core/api/api_client.dart';
import 'job_models.dart';

/// Read access to the technician's jobs.
///
/// M2: add a caching implementation (Drift `cached_jobs`, scoped by org) that
/// wraps [ApiJobsRepository] and falls back to the cache on `NetworkException`.
/// UI code must only depend on this interface via `jobsRepositoryProvider`.
abstract class JobsRepository {
  Future<AssignmentPage> listAssignments({
    required AssignmentScope scope,
    int page = 1,
    int pageSize = 20,
  });

  Future<JobDetail> getJob(String requestId);
}

class ApiJobsRepository implements JobsRepository {
  ApiJobsRepository(this._api);
  final ApiClient _api;

  @override
  Future<AssignmentPage> listAssignments({
    required AssignmentScope scope,
    int page = 1,
    int pageSize = 20,
  }) async => AssignmentPage.fromJson(
    await _api.getJson(
      '/me/assignments',
      query: {'scope': scope.name, 'page': page, 'page_size': pageSize},
    ),
  );

  @override
  Future<JobDetail> getJob(String requestId) async =>
      JobDetail.fromJson(await _api.getJson('/requests/$requestId'));
}
