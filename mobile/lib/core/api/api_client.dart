import 'package:dio/dio.dart';

import '../config/app_config.dart';
import 'api_exception.dart';

/// Supplies per-request auth context. Read lazily so org switches and
/// sign-in/out take effect without rebuilding Dio.
typedef AuthContext = ({String? token, String? orgId});

/// Adds `Authorization: Bearer` and `X-Org-Id`. Never logs the token.
class AuthInterceptor extends Interceptor {
  AuthInterceptor(this._context);
  final AuthContext Function() _context;

  @override
  void onRequest(RequestOptions options, RequestInterceptorHandler handler) {
    final ctx = _context();
    if (ctx.token != null && options.extra['skipAuth'] != true) {
      options.headers['Authorization'] = 'Bearer ${ctx.token}';
      if (ctx.orgId != null && options.extra['skipOrg'] != true) {
        options.headers['X-Org-Id'] = ctx.orgId;
      }
    }
    handler.next(options);
  }
}

/// Maps Dio failures to [AppException] (stored in `DioException.error`) and
/// reports side-channel signals (401 on an authenticated call, connectivity).
class ErrorMappingInterceptor extends Interceptor {
  ErrorMappingInterceptor({this.onUnauthorized, this.onNetworkResult});

  /// Called when an authenticated request returned 401 (session expired).
  final void Function()? onUnauthorized;

  /// `true` after any HTTP response, `false` after a connection failure.
  final void Function(bool reachable)? onNetworkResult;

  @override
  void onResponse(Response response, ResponseInterceptorHandler handler) {
    onNetworkResult?.call(true);
    handler.next(response);
  }

  @override
  void onError(DioException err, ErrorInterceptorHandler handler) {
    final mapped = mapDioException(err);
    if (mapped is NetworkException) {
      onNetworkResult?.call(false);
    } else {
      onNetworkResult?.call(true);
      if (mapped is ApiException &&
          mapped.isUnauthorized &&
          err.requestOptions.headers.containsKey('Authorization')) {
        onUnauthorized?.call();
      }
    }
    handler.next(err.copyWith(error: mapped));
  }
}

/// Pure mapping, exposed for tests.
AppException mapDioException(DioException e) {
  if (e.error is AppException) return e.error! as AppException;
  final response = e.response;
  if (response != null) {
    final status = response.statusCode ?? 0;
    final data = response.data;
    if (data is Map && data['error'] is Map) {
      final err = data['error'] as Map;
      return ApiException(
        status: status,
        code: (err['code'] ?? 'error').toString(),
        message: (err['message'] ?? 'Request failed.').toString(),
        details: err['details'],
        requestId: err['request_id']?.toString(),
      );
    }
    return ApiException(
      status: status,
      code: 'http_$status',
      message: 'Unexpected server response ($status).',
    );
  }
  switch (e.type) {
    case DioExceptionType.connectionTimeout:
    case DioExceptionType.sendTimeout:
    case DioExceptionType.receiveTimeout:
      return const NetworkException(
        'The server took too long to respond.',
        true,
      );
    case DioExceptionType.cancel:
      return const NetworkException('Request cancelled.');
    default:
      return const NetworkException();
  }
}

/// Thin JSON wrapper over Dio; all methods throw only [AppException]s.
class ApiClient {
  ApiClient(this.dio);
  final Dio dio;

  static Dio buildDio({
    required String baseUrl,
    required AuthContext Function() authContext,
    void Function()? onUnauthorized,
    void Function(bool reachable)? onNetworkResult,
    HttpClientAdapter? adapter,
  }) {
    final dio = Dio(
      BaseOptions(
        baseUrl: normalizeServerUrl(baseUrl) + AppConfig.apiPrefix,
        connectTimeout: const Duration(seconds: 10),
        receiveTimeout: const Duration(seconds: 20),
        sendTimeout: const Duration(seconds: 20),
        headers: {'Accept': 'application/json'},
        validateStatus: (s) => s != null && s >= 200 && s < 300,
      ),
    );
    if (adapter != null) dio.httpClientAdapter = adapter;
    dio.interceptors.addAll([
      AuthInterceptor(authContext),
      ErrorMappingInterceptor(
        onUnauthorized: onUnauthorized,
        onNetworkResult: onNetworkResult,
      ),
    ]);
    return dio;
  }

  Future<Map<String, dynamic>> getJson(
    String path, {
    Map<String, dynamic>? query,
  }) => _send(() => dio.get<Object?>(path, queryParameters: query));

  Future<Map<String, dynamic>> postJson(
    String path, {
    Object? body,
    Options? options,
  }) => _send(() => dio.post<Object?>(path, data: body, options: options));

  /// Multipart POST (file uploads).
  Future<Map<String, dynamic>> postForm(String path, FormData form) =>
      _send(() => dio.post<Object?>(path, data: form));

  /// POST whose success body is ignored (e.g. 204 logout).
  Future<void> postVoid(String path, {Object? body}) =>
      _send(() => dio.post<Object?>(path, data: body), allowEmpty: true);

  Future<Map<String, dynamic>> _send(
    Future<Response<Object?>> Function() call, {
    bool allowEmpty = false,
  }) async {
    try {
      final res = await call();
      final data = res.data;
      if (data is Map<String, dynamic>) return data;
      if (allowEmpty || data == null || data == '') return const {};
      throw const ApiException(
        status: 200,
        code: 'bad_response',
        message: 'The server returned an unexpected response.',
      );
    } on DioException catch (e) {
      throw mapDioException(e);
    }
  }
}
