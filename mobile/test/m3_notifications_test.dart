import 'package:fixflow_tech/core/api/api_client.dart';
import 'package:fixflow_tech/core/util/formatters.dart';
import 'package:fixflow_tech/features/notifications/notifications_repository.dart';
import 'package:fixflow_tech/features/notifications/notifications_screen.dart';
import 'package:fixflow_tech/features/profile/availability.dart';
import 'package:fixflow_tech/features/profile/availability_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/fake_adapter.dart';
import 'support/m3_fakes.dart';
import 'support/m3_support.dart';

Future<M3Rig> pumpWithNotifs(
  WidgetTester t,
  List<NotificationItem> items, {
  bool offline = false,
}) => pumpM3(
  t,
  offline: offline,
  detail: detailWith(actions: ['accept', 'decline', 'add_note']),
  notifications: FakeNotificationsRepository(items),
);

void main() {
  setUpAll(initTimezones);

  group('notifications', () {
    testWidgets('bell shows the unread count badge on the inbox', (t) async {
      await pumpWithNotifs(t, [
        notif('a'),
        notif('b'),
        notif('c', unread: false),
      ]);
      expect(find.text('2'), findsOneWidget); // badge
      expect(find.byTooltip('Notifications, 2 unread'), findsOneWidget);
      await unmountApp(t);
    });

    testWidgets('no badge when everything is read', (t) async {
      await pumpWithNotifs(t, [notif('a', unread: false)]);
      expect(find.byTooltip('Notifications'), findsOneWidget);
      expect(
        t
            .widget<Badge>(
              find.descendant(
                of: find.byType(NotificationsBell),
                matching: find.byType(Badge),
              ),
            )
            .isLabelVisible,
        isFalse,
      );
      await unmountApp(t);
    });

    testWidgets('list: unread highlighted with icon + text, read plain', (
      t,
    ) async {
      await pumpWithNotifs(t, [
        notif('a', title: 'New job assigned'),
        notif(
          'b',
          unread: false,
          type: 'ASSIGNMENT_RESCHEDULED',
          title: 'Job rescheduled',
        ),
      ]);
      await t.tap(find.byTooltip('Notifications, 1 unread'));
      await t.pumpAndSettle();
      expect(find.text('Notifications'), findsOneWidget);
      expect(find.text('New job assigned'), findsOneWidget);
      expect(find.text('Job rescheduled'), findsOneWidget);
      expect(find.text('Unread'), findsOneWidget);
      expect(find.text('Read'), findsOneWidget);
      expect(find.byIcon(Icons.assignment_ind_outlined), findsOneWidget);
      expect(find.byIcon(Icons.event_repeat), findsOneWidget);
      await unmountApp(t);
    });

    testWidgets('tap marks read, updates the badge and opens the job', (
      t,
    ) async {
      final rig = await pumpWithNotifs(t, [notif('a'), notif('b')]);
      await t.tap(find.byTooltip('Notifications, 2 unread'));
      await t.pumpAndSettle();
      await t.tap(find.text('Body of a'));
      await t.pumpAndSettle();
      expect(rig.notifications.marked, ['a']);
      // landed on the job detail
      expect(find.text('Repair the stuck service door'), findsOneWidget);
      await t.pageBack();
      await t.pumpAndSettle();
      expect(find.text('Unread'), findsOneWidget); // only b is left unread
      await t.pageBack();
      await t.pumpAndSettle();
      expect(find.byTooltip('Notifications, 1 unread'), findsOneWidget);
      await unmountApp(t);
    });

    testWidgets('notification without a job only marks read', (t) async {
      final rig = await pumpWithNotifs(t, [notif('a', requestId: null)]);
      await t.tap(find.byTooltip('Notifications, 1 unread'));
      await t.pumpAndSettle();
      await t.tap(find.text('Body of a'));
      await t.pumpAndSettle();
      expect(rig.notifications.marked, ['a']);
      expect(find.text('Notifications'), findsOneWidget);
      expect(find.text('Unread'), findsNothing);
      await unmountApp(t);
    });

    testWidgets('mark all read', (t) async {
      final rig = await pumpWithNotifs(t, [notif('a'), notif('b')]);
      await t.tap(find.byTooltip('Notifications, 2 unread'));
      await t.pumpAndSettle();
      await t.tap(find.text('Mark all read'));
      await t.pumpAndSettle();
      expect(rig.notifications.markAllCalls, 1);
      expect(find.text('Unread'), findsNothing);
      expect(
        t
            .widget<TextButton>(
              find.widgetWithText(TextButton, 'Mark all read'),
            )
            .onPressed,
        isNull,
      );
      await t.pageBack();
      await t.pumpAndSettle();
      expect(find.byTooltip('Notifications'), findsOneWidget);
      await unmountApp(t);
    });

    testWidgets('empty state', (t) async {
      await pumpWithNotifs(t, []);
      await t.tap(find.byTooltip('Notifications'));
      await t.pumpAndSettle();
      expect(find.text('No notifications'), findsOneWidget);
      await unmountApp(t);
    });

    testWidgets('unread count is refreshed when the app resumes', (t) async {
      final rig = await pumpWithNotifs(t, [notif('a')]);
      final before = rig.notifications.unreadCalls;
      rig.notifications.items = [notif('a'), notif('b'), notif('c')];
      t.binding.handleAppLifecycleStateChanged(AppLifecycleState.inactive);
      t.binding.handleAppLifecycleStateChanged(AppLifecycleState.hidden);
      t.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
      t.binding.handleAppLifecycleStateChanged(AppLifecycleState.hidden);
      t.binding.handleAppLifecycleStateChanged(AppLifecycleState.inactive);
      t.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
      await t.pumpAndSettle();
      expect(rig.notifications.unreadCalls, greaterThan(before));
      expect(find.byTooltip('Notifications, 3 unread'), findsOneWidget);
      await unmountApp(t);
    });

    test('wire contract: list, unread-count, read, read-all', () async {
      final a = FakeAdapter((o) {
        if (o.path.endsWith('/unread-count')) {
          return FakeAdapter.json(200, {'unread': 4});
        }
        if (o.path.endsWith('/read-all')) {
          return FakeAdapter.json(200, {'marked': 2});
        }
        if (o.path.endsWith('/read')) {
          return FakeAdapter.json(200, {
            'id': 'n1',
            'type': 'ASSIGNMENT_CREATED',
            'title': 't',
            'body': 'b',
            'request_id': null,
            'read_at': '2026-11-15T09:00:00Z',
            'created_at': '2026-11-15T08:00:00Z',
          });
        }
        return FakeAdapter.json(200, {
          'items': [
            {
              'id': 'n1',
              'type': 'ASSIGNMENT_CREATED',
              'title': 'New job assigned',
              'body': 'b',
              'request_id': 'r1',
              'data': null,
              'read_at': null,
              'created_at': '2026-11-15T08:00:00Z',
            },
          ],
          'total': 1,
          'page': 1,
          'page_size': 50,
        });
      });
      final repo = ApiNotificationsRepository(
        ApiClient(
          ApiClient.buildDio(
            baseUrl: 'http://fake',
            authContext: () => (token: 't', orgId: 'o'),
            adapter: a,
          ),
        ),
      );
      final items = await repo.list();
      expect(items.single.unread, isTrue);
      expect(items.single.requestId, 'r1');
      expect(await repo.unreadCount(), 4);
      expect((await repo.markRead('n1')).unread, isFalse);
      await repo.markAllRead();
      expect(
        a.requests.map((o) => '${o.method} ${o.path.split('/api/v1').last}'),
        [
          'GET /notifications',
          'GET /notifications/unread-count',
          'POST /notifications/n1/read',
          'POST /notifications/read-all',
        ],
      );
    });
  });

  group('availability', () {
    final profile = TechnicianProfile.fromJson({
      'skills': [
        {'id': '1', 'name': 'electrical'},
        {'id': '2', 'name': 'general'},
      ],
      'availability': [
        for (var d = 0; d < 5; d++)
          {
            'id': '$d',
            'weekday': d,
            'start_time': '09:00:00',
            'end_time': '18:00:00',
          },
      ],
      'time_off': [
        {
          'id': 't1',
          'start_at': '2099-01-10T04:00:00Z',
          'end_at': '2099-01-12T12:00:00Z',
          'reason': 'Annual leave',
        },
        {
          'id': 't0',
          'start_at': '2020-01-10T04:00:00Z',
          'end_at': '2020-01-12T12:00:00Z',
          'reason': 'Long ago',
        },
      ],
    });

    testWidgets(
      'renders skills, weekly hours in org tz and upcoming time off',
      (t) async {
        await pumpM3(
          t,
          detail: detailWith(actions: []),
          technician: FakeTechnicianRepository(profile),
        );
        await t.tap(find.byTooltip('Profile'));
        await t.pumpAndSettle();
        await t.tap(find.text('My availability'));
        await t.pumpAndSettle();
        expect(find.text('My availability'), findsOneWidget);
        expect(find.text('Electrical'), findsOneWidget);
        expect(find.text('General'), findsOneWidget);
        expect(find.textContaining('(Asia/Bishkek)'), findsOneWidget);
        expect(find.text('Monday'), findsOneWidget);
        expect(find.text('Sunday'), findsOneWidget);
        expect(find.text('09:00–18:00'), findsNWidgets(5));
        expect(find.text('Not available'), findsNWidgets(2)); // Sat, Sun
        // 2099-01-10 04:00Z == 10:00 in Asia/Bishkek (UTC+6)
        expect(find.textContaining('10 Jan 2099, 10:00'), findsOneWidget);
        expect(find.textContaining('Annual leave'), findsOneWidget);
        expect(find.textContaining('Long ago'), findsNothing);
        await unmountApp(t);
      },
    );

    testWidgets('empty profile explains itself', (t) async {
      await t.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: AvailabilityView(
              profile: const TechnicianProfile(
                skills: [],
                availability: [],
                timeOff: [],
              ),
              timezone: 'Asia/Bishkek',
            ),
          ),
        ),
      );
      expect(find.text('No skills recorded.'), findsOneWidget);
      expect(find.text('No upcoming time off.'), findsOneWidget);
      expect(find.text('Not available'), findsNWidgets(7));
    });
  });
}
