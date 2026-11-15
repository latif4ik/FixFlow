import '../api/api_client.dart';
import '../api/api_exception.dart';
import 'models.dart';

/// Auth endpoints. Throws only [AppException]s.
class AuthRepository {
  AuthRepository(this._api);
  final ApiClient _api;

  Future<LoginResult> login(String email, String password) async {
    final json = await _api.postJson(
      '/auth/login',
      body: {'email': email.trim(), 'password': password},
    );
    return LoginResult.fromJson(json);
  }

  /// Best effort: the local sign-out must succeed even when offline.
  Future<void> logout() async {
    try {
      await _api.postVoid('/auth/logout');
    } on AppException {
      // Token may already be invalid/expired or the server unreachable.
    }
  }
}
