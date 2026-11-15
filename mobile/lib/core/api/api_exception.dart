/// Typed errors surfaced by the API layer. Repositories and UI only deal with
/// these, never with raw Dio exceptions.
sealed class AppException implements Exception {
  const AppException(this.message);
  final String message;

  @override
  String toString() => '$runtimeType: $message';
}

/// Server answered with the standard error envelope
/// `{"error": {"code", "message", "details", "request_id"}}`.
class ApiException extends AppException {
  const ApiException({
    required this.status,
    required this.code,
    required String message,
    this.details,
    this.requestId,
  }) : super(message);

  final int status;
  final String code;
  final Object? details;
  final String? requestId;

  bool get isUnauthorized => status == 401;
  bool get isForbidden => status == 403;
  bool get isNotFound => status == 404;
  bool get isConflict => status == 409;
  bool get isServerError => status >= 500;
}

/// No usable response: connection refused, DNS failure, timeout, offline.
/// Treated as "offline" by the UI and (M2) as retryable by the sync queue.
class NetworkException extends AppException {
  const NetworkException([
    super.message = 'Cannot reach the server.',
    this.timedOut = false,
  ]);

  final bool timedOut;
}
