import 'package:dio/dio.dart';
import 'package:fixflow_tech/app.dart';
import 'package:fixflow_tech/core/api/api_client.dart';
import 'package:fixflow_tech/core/providers.dart';
import 'package:fixflow_tech/core/util/formatters.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/fake_adapter.dart';
import 'support/fixtures.dart';
import 'support/harness.dart';

Future<ProviderContainer> container(FakeAdapter adapter) async {
  final overrides = await baseOverrides();
  final c = ProviderContainer(
    overrides: [
      ...overrides,
      apiClientProvider.overrideWith(
        (ref) => ApiClient(
          ApiClient.buildDio(
            baseUrl: 'http://x',
            authContext: () => (
              token: ref.read(sessionProvider).token,
              orgId: ref.read(sessionProvider).selectedOrgId,
            ),
            onUnauthorized: () =>
                ref.read(sessionProvider.notifier).markExpired(),
            adapter: adapter,
          ),
        ),
      ),
    ],
  );
  addTearDown(c.dispose);
  return c;
}

Future<void> settle(ProviderContainer c) async {
  c.read(sessionProvider);
  await Future<void>.delayed(const Duration(milliseconds: 50));
}

void main() {
  setUpAll(initTimezones);

  group('session controller', () {
    test('sign-in persists token + session; sign-out clears them', () async {
      final a = FakeAdapter((o) {
        if (o.path.endsWith('/auth/login')) {
          return FakeAdapter.json(200, loginJson());
        }
        return ResponseBody.fromString('', 204);
      });
      final c = await container(a);
      await settle(c);
      expect(c.read(sessionProvider).status, SessionStatus.signedOut);

      await c.read(sessionProvider.notifier).signIn('tech@x.demo', 'pw');
      var s = c.read(sessionProvider);
      expect(s.isSignedIn, isTrue);
      expect(s.selectedOrgId, 'o1'); // single technician org auto-selected
      expect(await c.read(tokenStoreProvider).read(), 'tok-123');
      expect(await c.read(sessionStoreProvider).load(), isNotNull);
      expect(s.toString(), isNot(contains('tok-123')));

      await c.read(sessionProvider.notifier).signOut();
      s = c.read(sessionProvider);
      expect(s.status, SessionStatus.signedOut);
      expect(s.lastEmail, 'tech@x.demo');
      expect(await c.read(tokenStoreProvider).read(), isNull);
      expect(await c.read(sessionStoreProvider).load(), isNull);
      expect(a.requests.any((r) => r.path.endsWith('/auth/logout')), isTrue);
    });

    test(
      '401 on an authenticated call moves to expired and keeps queued work',
      () async {
        final a = FakeAdapter((o) {
          if (o.path.endsWith('/auth/login')) {
            return FakeAdapter.json(200, loginJson());
          }
          return FakeAdapter.json(401, {
            'error': {'code': 'unauthorized', 'message': 'expired'},
          });
        });
        final c = await container(a);
        await settle(c);
        await c.read(sessionProvider.notifier).signIn('tech@x.demo', 'pw');
        // A queued offline command must survive expiry.
        final db = c.read(appDatabaseProvider);
        await db.customStatement(
          "INSERT INTO pending_commands (client_command_id, org_id, request_id, type, payload_json, created_at, updated_at) VALUES ('c1','o1','r1','ADD_NOTE','{}',1,1)",
        );
        await expectLater(
          c.read(apiClientProvider).getJson('/me/assignments'),
          throwsA(anything),
        );
        await Future<void>.delayed(const Duration(milliseconds: 20));
        expect(c.read(sessionProvider).status, SessionStatus.expired);
        expect(await c.read(tokenStoreProvider).read(), isNull);
        final rows = await db.select(db.pendingCommands).get();
        expect(rows, hasLength(1));

        // Signing out afterwards also keeps queued work.
        await c.read(sessionProvider.notifier).signOut();
        expect(await db.select(db.pendingCommands).get(), hasLength(1));
      },
    );

    test('switching org updates selection and persists it', () async {
      final a = FakeAdapter(
        (o) => FakeAdapter.json(
          200,
          loginJson(
            memberships: [
              membershipJson('o1', 'TECHNICIAN'),
              membershipJson('o2', 'TECHNICIAN'),
            ],
          ),
        ),
      );
      final c = await container(a);
      await settle(c);
      await c.read(sessionProvider.notifier).signIn('tech@x.demo', 'pw');
      expect(c.read(sessionProvider).route, OrgRoute.selectOrg);
      await c.read(sessionProvider.notifier).selectOrg('o2');
      expect(c.read(sessionProvider).selectedOrgId, 'o2');
      expect((await c.read(sessionStoreProvider).load())!.selectedOrgId, 'o2');
      await c.read(sessionProvider.notifier).selectOrg('not-mine');
      expect(c.read(sessionProvider).selectedOrgId, 'o2');
    });
  });

  group('sign-in screen', () {
    Future<void> pump(WidgetTester t, FakeAdapter adapter) async {
      final overrides = await baseOverrides();
      await t.pumpWidget(
        ProviderScope(
          overrides: [
            ...overrides,
            apiClientProvider.overrideWith(
              (ref) => ApiClient(
                ApiClient.buildDio(
                  baseUrl: 'http://x',
                  authContext: () => (token: null, orgId: null),
                  adapter: adapter,
                ),
              ),
            ),
          ],
          child: const FixFlowApp(),
        ),
      );
      await t.pumpAndSettle();
    }

    testWidgets('validates empty fields without calling the server', (t) async {
      final a = FakeAdapter((_) => FakeAdapter.json(200, loginJson()));
      await pump(t, a);
      expect(find.text('Sign in'), findsWidgets);
      await t.tap(find.widgetWithText(FilledButton, 'Sign in'));
      await t.pumpAndSettle();
      expect(find.text('Enter your email.'), findsOneWidget);
      expect(find.text('Enter your password.'), findsOneWidget);
      expect(a.requests, isEmpty);
    });

    testWidgets('invalid credentials show a generic message', (t) async {
      final a = FakeAdapter(
        (_) => FakeAdapter.json(401, {
          'error': {
            'code': 'unauthorized',
            'message': 'Invalid email or password.',
          },
        }),
      );
      await pump(t, a);
      await t.enterText(
        find.widgetWithText(TextFormField, 'Email'),
        'tech@x.demo',
      );
      await t.enterText(
        find.widgetWithText(TextFormField, 'Password'),
        'wrong',
      );
      await t.tap(find.widgetWithText(FilledButton, 'Sign in'));
      await t.pumpAndSettle();
      expect(find.text('Invalid email or password.'), findsOneWidget);
    });

    testWidgets('unreachable server explains the API URL', (t) async {
      final a = FakeAdapter(
        (o) => throw DioException(
          requestOptions: o,
          type: DioExceptionType.connectionError,
        ),
      );
      await pump(t, a);
      await t.enterText(
        find.widgetWithText(TextFormField, 'Email'),
        'tech@x.demo',
      );
      await t.enterText(find.widgetWithText(TextFormField, 'Password'), 'pw');
      await t.tap(find.widgetWithText(FilledButton, 'Sign in'));
      await t.pumpAndSettle();
      expect(find.textContaining('Cannot reach the server'), findsOneWidget);
      expect(find.textContaining('10.0.2.2'), findsWidgets);
    });

    testWidgets('server setting validates and persists the URL', (t) async {
      await pump(t, FakeAdapter((_) => FakeAdapter.json(200, {})));
      await t.tap(find.text('Server'));
      await t.pumpAndSettle();
      final field = find.widgetWithText(TextFormField, 'Server address');
      await t.enterText(field, 'not a url');
      await t.ensureVisible(find.text('Save server'));
      await t.tap(find.text('Save server'));
      await t.pumpAndSettle();
      expect(find.textContaining('full address'), findsOneWidget);
      await t.enterText(field, 'http://192.168.1.20:8000/');
      await t.ensureVisible(find.text('Save server'));
      await t.tap(find.text('Save server'));
      await t.pumpAndSettle();
      expect(
        find.text('Server set to http://192.168.1.20:8000'),
        findsOneWidget,
      );
    });

    testWidgets(
      'account without technician membership sees guidance and sign-out',
      (t) async {
        final a = FakeAdapter(
          (_) => FakeAdapter.json(
            200,
            loginJson(memberships: [membershipJson('o1', 'ADMIN')]),
          ),
        );
        await pump(t, a);
        await t.enterText(
          find.widgetWithText(TextFormField, 'Email'),
          'tech@x.demo',
        );
        await t.enterText(find.widgetWithText(TextFormField, 'Password'), 'pw');
        await t.tap(find.widgetWithText(FilledButton, 'Sign in'));
        await t.pumpAndSettle();
        expect(
          find.text('This app is for technicians; use the web app.'),
          findsOneWidget,
        );
        expect(find.text('Sign out'), findsOneWidget);
      },
    );
  });
}
