import 'package:drift/native.dart';
import 'package:fixflow_tech/core/api/api_exception.dart';
import 'package:fixflow_tech/core/auth/models.dart';
import 'package:fixflow_tech/core/auth/session_controller.dart';
import 'package:fixflow_tech/core/auth/token_store.dart';
import 'package:fixflow_tech/core/db/database.dart';
import 'package:fixflow_tech/core/providers.dart';
import 'package:fixflow_tech/features/jobs/job_models.dart';
import 'package:fixflow_tech/features/jobs/jobs_providers.dart';
import 'package:fixflow_tech/features/jobs/jobs_repository.dart';
import 'package:fixflow_tech/features/notifications/notifications_providers.dart';
import 'package:fixflow_tech/features/notifications/notifications_repository.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:shared_preferences/shared_preferences.dart';

import 'fixtures.dart';
import 'm3_fakes.dart';

/// Session notifier with a fixed initial state (no storage involved).
class FakeSession extends SessionController {
  FakeSession(this.initial);
  final SessionState initial;
  @override
  SessionState build() => initial;
}

class FakeJobsRepository implements JobsRepository {
  FakeJobsRepository({
    this.pages = const {},
    this.detail,
    this.detailError,
    this.listError,
  });
  final Map<AssignmentScope, List<AssignmentItem>> pages;
  JobDetail? detail;
  int detailCalls = 0;
  final Object? detailError;
  final Object? listError;
  int listCalls = 0;

  @override
  Future<AssignmentPage> listAssignments({
    required AssignmentScope scope,
    int page = 1,
    int pageSize = 20,
  }) async {
    listCalls++;
    if (listError != null) throw listError!;
    final items = pages[scope] ?? const [];
    return AssignmentPage(
      items: items,
      total: items.length,
      page: page,
      pageSize: pageSize,
    );
  }

  @override
  Future<JobDetail> getJob(String requestId) async {
    detailCalls++;
    if (detailError != null) throw detailError!;
    return detail!;
  }
}

SessionState technicianSession() => SessionState(
  status: SessionStatus.signedIn,
  token: 't',
  user: const UserProfile(id: 'u', email: 'tech@x.demo', fullName: 'Tech One'),
  memberships: [membership('o1', 'TECHNICIAN')],
  selectedOrgId: 'o1',
);

Future<List<Override>> baseOverrides({
  SessionState? session,
  JobsRepository? repo,
  NotificationsRepository? notifications,
}) async {
  SharedPreferences.setMockInitialValues({});
  final prefs = await SharedPreferences.getInstance();
  return [
    sharedPreferencesProvider.overrideWithValue(prefs),
    appDatabaseProvider.overrideWith((ref) {
      final db = AppDatabase(NativeDatabase.memory());
      ref.onDispose(db.close);
      return db;
    }),
    tokenStoreProvider.overrideWithValue(InMemoryTokenStore()),
    connectivityProvider.overrideWith((ref) => Stream.value(true)),
    if (session != null)
      sessionProvider.overrideWith(() => FakeSession(session)),
    if (repo != null) jobsRepositoryProvider.overrideWithValue(repo),
    // Never hit the network from widget tests unless a test overrides this.
    notificationsRepositoryProvider.overrideWithValue(
      notifications ?? FakeNotificationsRepository(),
    ),
  ];
}

ApiException apiError(int status, [String message = 'err']) =>
    ApiException(status: status, code: 'e', message: message);
