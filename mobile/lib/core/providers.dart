import 'dart:async';

import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'api/api_client.dart';
import 'auth/auth_repository.dart';
import 'auth/session.dart';
import 'auth/session_controller.dart';
import 'auth/session_store.dart';
import 'auth/token_store.dart';
import 'config/app_config.dart';
import 'db/database.dart';

export 'auth/session.dart';

/// Overridden in `main()` (and in tests) with real instances.
final sharedPreferencesProvider = Provider<SharedPreferences>(
  (ref) => throw UnimplementedError('sharedPreferencesProvider not overridden'),
);

final appDatabaseProvider = Provider<AppDatabase>((ref) {
  final db = AppDatabase.open();
  ref.onDispose(db.close);
  return db;
});

final tokenStoreProvider = Provider<TokenStore>((ref) => SecureTokenStore());

final sessionStoreProvider = Provider<SessionStore>(
  (ref) => SessionStore(ref.watch(appDatabaseProvider)),
);

/// Persisted API base URL (in-app "Server" setting).
class ServerUrlController extends Notifier<String> {
  static const prefsKey = 'server_url';

  @override
  String build() =>
      ref.watch(sharedPreferencesProvider).getString(prefsKey) ??
      AppConfig.defaultBaseUrl;

  /// Caller must validate with `validateServerUrl` first.
  Future<void> set(String url) async {
    final normalized = normalizeServerUrl(url);
    await ref.read(sharedPreferencesProvider).setString(prefsKey, normalized);
    state = normalized;
  }

  Future<void> reset() async {
    await ref.read(sharedPreferencesProvider).remove(prefsKey);
    state = AppConfig.defaultBaseUrl;
  }
}

final serverUrlProvider = NotifierProvider<ServerUrlController, String>(
  ServerUrlController.new,
);

final sessionProvider = NotifierProvider<SessionController, SessionState>(
  SessionController.new,
);

/// Selected organization id (null when signed out / not chosen yet). Data
/// providers watch this so an org switch drops their state automatically.
final selectedOrgIdProvider = Provider<String?>(
  (ref) => ref.watch(sessionProvider.select((s) => s.selectedOrgId)),
);

/// Dev tool (M2 demo): force the app to behave as if offline.
class SimulateOffline extends Notifier<bool> {
  @override
  bool build() => false;
  void set(bool v) => state = v;
}

final simulateOfflineProvider = NotifierProvider<SimulateOffline, bool>(
  SimulateOffline.new,
);

/// Outcome of the most recent HTTP attempt: false = connection failure.
class NetworkReachable extends Notifier<bool> {
  @override
  bool build() => true;
  void report(bool reachable) {
    if (state != reachable) state = reachable;
  }
}

final networkReachableProvider = NotifierProvider<NetworkReachable, bool>(
  NetworkReachable.new,
);

/// Device connectivity (radio level). `true` when any transport is up.
final connectivityProvider = StreamProvider<bool>((ref) async* {
  final c = Connectivity();
  bool up(List<ConnectivityResult> r) =>
      r.any((e) => e != ConnectivityResult.none);
  yield up(await c.checkConnectivity());
  yield* c.onConnectivityChanged.map(up);
});

/// Single source of truth for the offline banner and offline-only logic.
final isOfflineProvider = Provider<bool>((ref) {
  if (ref.watch(simulateOfflineProvider)) return true;
  final radio = ref.watch(connectivityProvider).asData?.value ?? true;
  final reachable = ref.watch(networkReachableProvider);
  return !radio || !reachable;
});

/// Dio configured for the current server URL; auth context is read lazily.
final dioProvider = Provider<Dio>((ref) {
  final baseUrl = ref.watch(serverUrlProvider);
  return ApiClient.buildDio(
    baseUrl: baseUrl,
    authContext: () {
      final s = ref.read(sessionProvider);
      return (token: s.token, orgId: s.selectedOrgId);
    },
    onUnauthorized: () => ref.read(sessionProvider.notifier).markExpired(),
    onNetworkResult: (ok) =>
        ref.read(networkReachableProvider.notifier).report(ok),
  );
});

final apiClientProvider = Provider<ApiClient>((ref) {
  final api = ApiClient(ref.watch(dioProvider));
  // Dev tool: simulated offline short-circuits every request.
  api.dio.interceptors.insert(
    0,
    InterceptorsWrapper(
      onRequest: (o, h) {
        if (ref.read(simulateOfflineProvider)) {
          h.reject(
            DioException(
              requestOptions: o,
              type: DioExceptionType.connectionError,
            ),
          );
        } else {
          h.next(o);
        }
      },
    ),
  );
  return api;
});

final authRepositoryProvider = Provider<AuthRepository>(
  (ref) => AuthRepository(ref.watch(apiClientProvider)),
);
