import 'package:dio/dio.dart';
import 'package:fixflow_tech/core/api/api_client.dart';
import 'package:fixflow_tech/core/api/api_exception.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/fake_adapter.dart';

ApiClient client(
  FakeAdapter adapter, {
  String? token = 'secret-token',
  String? org = 'org-1',
  void Function()? onUnauthorized,
  void Function(bool)? onNet,
}) => ApiClient(
  ApiClient.buildDio(
    baseUrl: 'http://10.0.2.2:8000/',
    authContext: () => (token: token, orgId: org),
    onUnauthorized: onUnauthorized,
    onNetworkResult: onNet,
    adapter: adapter,
  ),
);

void main() {
  test('adds Bearer and X-Org-Id and builds the /api/v1 URL', () async {
    final a = FakeAdapter((_) => FakeAdapter.json(200, {'ok': true}));
    await client(a).getJson('/me/assignments', query: {'scope': 'active'});
    final r = a.requests.single;
    expect(r.headers['Authorization'], 'Bearer secret-token');
    expect(r.headers['X-Org-Id'], 'org-1');
    expect(
      r.uri.toString(),
      'http://10.0.2.2:8000/api/v1/me/assignments?scope=active',
    );
  });

  test('no auth headers without a token', () async {
    final a = FakeAdapter((_) => FakeAdapter.json(200, {}));
    await client(a, token: null).postJson('/auth/login', body: {});
    expect(a.requests.single.headers.containsKey('Authorization'), isFalse);
  });

  test('maps the error envelope to ApiException', () async {
    final a = FakeAdapter(
      (_) => FakeAdapter.json(409, {
        'error': {
          'code': 'conflict',
          'message': 'Already taken',
          'details': [
            {'field': 'x'},
          ],
          'request_id': 'req-9',
        },
      }),
    );
    final f = client(a).getJson('/x');
    await expectLater(
      f,
      throwsA(
        isA<ApiException>()
            .having((e) => e.status, 'status', 409)
            .having((e) => e.code, 'code', 'conflict')
            .having((e) => e.message, 'message', 'Already taken')
            .having((e) => e.requestId, 'requestId', 'req-9')
            .having((e) => e.details, 'details', isA<List>())
            .having((e) => e.isConflict, 'isConflict', isTrue),
      ),
    );
  });

  test('401 on an authenticated request signals session expiry', () async {
    var expired = 0;
    final a = FakeAdapter(
      (_) => FakeAdapter.json(401, {
        'error': {'code': 'unauthorized', 'message': 'Bad token'},
      }),
    );
    await expectLater(
      client(a, onUnauthorized: () => expired++).getJson('/x'),
      throwsA(isA<ApiException>().having((e) => e.isUnauthorized, '401', true)),
    );
    expect(expired, 1);
  });

  test('401 on an unauthenticated request (login) does NOT expire', () async {
    var expired = 0;
    final a = FakeAdapter(
      (_) => FakeAdapter.json(401, {
        'error': {
          'code': 'unauthorized',
          'message': 'Invalid email or password.',
        },
      }),
    );
    await expectLater(
      client(
        a,
        token: null,
        onUnauthorized: () => expired++,
      ).postJson('/auth/login'),
      throwsA(isA<ApiException>()),
    );
    expect(expired, 0);
  });

  test(
    'connection errors become NetworkException and report unreachable',
    () async {
      final reports = <bool>[];
      final a = FakeAdapter(
        (o) => throw DioException(
          requestOptions: o,
          type: DioExceptionType.connectionError,
        ),
      );
      await expectLater(
        client(a, onNet: reports.add).getJson('/x'),
        throwsA(isA<NetworkException>()),
      );
      expect(reports, [false]);
    },
  );

  test('timeouts become NetworkException(timedOut)', () async {
    final a = FakeAdapter(
      (o) => throw DioException(
        requestOptions: o,
        type: DioExceptionType.receiveTimeout,
      ),
    );
    await expectLater(
      client(a).getJson('/x'),
      throwsA(
        isA<NetworkException>().having((e) => e.timedOut, 'timedOut', true),
      ),
    );
  });

  test('non-envelope error bodies still map to ApiException', () async {
    final a = FakeAdapter(
      (_) => ResponseBody.fromString('<html>bad gateway</html>', 502),
    );
    await expectLater(
      client(a).getJson('/x'),
      throwsA(
        isA<ApiException>()
            .having((e) => e.status, 'status', 502)
            .having((e) => e.isServerError, 'server', true),
      ),
    );
  });
}
