/// Compile-time and validation helpers for configuration.
///
/// The API base URL is NOT a secret. Default comes from
/// `--dart-define=API_BASE_URL=...`; users may override it in-app (persisted in
/// SharedPreferences, see `serverUrlProvider`).
class AppConfig {
  AppConfig._();

  /// Android emulator alias for the host machine's localhost.
  static const emulatorBaseUrl = 'http://10.0.2.2:8000';

  static const defaultBaseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: emulatorBaseUrl,
  );

  static const apiPrefix = '/api/v1';

  static const appName = 'FixFlow Tech';
}

/// Returns an error message when [input] is not a usable http(s) server URL,
/// otherwise null.
String? validateServerUrl(String? input) {
  final value = (input ?? '').trim();
  if (value.isEmpty) return 'Enter the server address.';
  final uri = Uri.tryParse(value);
  if (uri == null ||
      !(uri.scheme == 'http' || uri.scheme == 'https') ||
      uri.host.isEmpty) {
    return 'Use a full address such as http://192.168.1.20:8000';
  }
  if (uri.hasQuery || uri.fragment.isNotEmpty || uri.userInfo.isNotEmpty) {
    return 'Remove credentials, query or fragment from the address.';
  }
  return null;
}

/// Trims whitespace and trailing slashes so paths can be appended safely.
String normalizeServerUrl(String input) {
  var v = input.trim();
  while (v.endsWith('/')) {
    v = v.substring(0, v.length - 1);
  }
  return v;
}
