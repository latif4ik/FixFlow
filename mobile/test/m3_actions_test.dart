import 'dart:async';

import 'package:fixflow_tech/core/api/api_exception.dart';
import 'package:fixflow_tech/core/util/formatters.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/m3_fakes.dart';
import 'support/m3_support.dart';

const _estimateErr = ApiException(
  status: 409,
  code: 'estimate_not_approved',
  message: 'The estimate must be approved before work can start.',
  details: {'estimate_status': 'AWAITING_APPROVAL'},
);

void main() {
  setUpAll(initTimezones);

  group('actions follow allowed_actions', () {
    testWidgets('SCHEDULED: accept + decline + note, nothing else', (t) async {
      await pumpM3(
        t,
        detail: detailWith(actions: ['accept', 'decline', 'add_note']),
      );
      await openJob(t);
      await scrollTo(t, find.text('Available actions'));
      expect(find.text('Accept job'), findsOneWidget);
      expect(find.text('Decline job'), findsOneWidget);
      expect(find.text('Add note'), findsOneWidget);
      expect(find.text('Start work'), findsNothing);
      expect(find.text('Mark complete'), findsNothing);
      expect(find.text('Resume work'), findsNothing);
      expect(buttonEnabled(t, 'Accept job'), isTrue);
      await unmountApp(t);
    });

    testWidgets('IN_PROGRESS: block + complete', (t) async {
      await pumpM3(
        t,
        detail: detailWith(
          status: 'IN_PROGRESS',
          actions: ['block', 'complete', 'add_note'],
        ),
      );
      await openJob(t);
      await scrollTo(t, find.text('Available actions'));
      expect(find.text('Mark complete'), findsOneWidget);
      expect(find.text('Report a blocker'), findsOneWidget);
      expect(find.text('Accept job'), findsNothing);
      expect(find.text('Start work'), findsNothing);
      await unmountApp(t);
    });

    testWidgets('no actions: explains instead of showing controls', (t) async {
      await pumpM3(
        t,
        detail: detailWith(status: 'COMPLETED', actions: []),
      );
      await openJob(t);
      await scrollTo(t, find.text('Available actions'));
      expect(
        find.text('No actions are available for this job right now.'),
        findsOneWidget,
      );
      await unmountApp(t);
    });
  });

  testWidgets(
    'offline: every online-only action is disabled with an explanation',
    (t) async {
      final rig = await pumpM3(
        t,
        offline: true,
        detail: detailWith(actions: ['accept', 'decline', 'add_note']),
      );
      await openJob(t);
      await scrollTo(t, find.text('Available actions'));
      expect(buttonEnabled(t, 'Accept job'), isFalse);
      expect(buttonEnabled(t, 'Decline job'), isFalse);
      // notes still work offline (outbox)
      expect(buttonEnabled(t, 'Add note'), isTrue);
      expect(find.textContaining('Requires connection'), findsNWidgets(2));
      await t.tap(find.text('Accept job'), warnIfMissed: false);
      await t.pump();
      expect(rig.actions.calls, isEmpty);
      await unmountApp(t);
    },
  );

  group('transitions', () {
    testWidgets('accept: calls the server, then refreshes the job', (t) async {
      final rig = await pumpM3(
        t,
        detail: detailWith(actions: ['accept', 'decline', 'add_note']),
      );
      await openJob(t);
      final before = rig.repo.detailCalls;
      await scrollTo(t, find.text('Accept job'));
      await t.tap(find.text('Accept job'));
      await t.pumpAndSettle();
      expect(rig.actions.calls, ['accept']);
      expect(rig.repo.detailCalls, greaterThan(before));
      expect(find.text('Job accepted.'), findsOneWidget);
      await unmountApp(t);
    });

    testWidgets('double tap sends one request while it is in flight', (
      t,
    ) async {
      final gate = Completer<void>();
      final actions = FakeActionsRepository()..gate = gate.future;
      final rig = await pumpM3(
        t,
        actions: actions,
        detail: detailWith(actions: ['accept', 'decline', 'add_note']),
      );
      await openJob(t);
      await scrollTo(t, find.text('Accept job'));
      await t.tap(find.text('Accept job'));
      await t.pump();
      expect(buttonEnabled(t, 'Accept job…'), isFalse);
      expect(buttonEnabled(t, 'Decline job'), isFalse);
      await t.tap(find.text('Accept job…'), warnIfMissed: false);
      await t.pump();
      expect(rig.actions.calls, ['accept']);
      expect(find.text('Job accepted.'), findsNothing); // not yet
      gate.complete();
      await t.pumpAndSettle();
      expect(rig.actions.calls, ['accept']);
      expect(find.text('Job accepted.'), findsOneWidget);
      await unmountApp(t);
    });

    testWidgets('network failure shows an error and NO success', (t) async {
      final actions = FakeActionsRepository()..error = const NetworkException();
      await pumpM3(
        t,
        actions: actions,
        detail: detailWith(actions: ['accept', 'decline', 'add_note']),
      );
      await openJob(t);
      await scrollTo(t, find.text('Accept job'));
      await t.tap(find.text('Accept job'));
      await t.pumpAndSettle();
      expect(find.text('Could not accept the job'), findsOneWidget);
      expect(find.textContaining('Nothing was changed'), findsOneWidget);
      expect(find.text('Job accepted.'), findsNothing);
      await unmountApp(t);
    });

    testWidgets('invalid_transition conflict shows the server message', (
      t,
    ) async {
      final actions = FakeActionsRepository()
        ..error = const ApiException(
          status: 409,
          code: 'invalid_transition',
          message: 'A request cannot move from IN_PROGRESS to ACCEPTED.',
        );
      await pumpM3(
        t,
        actions: actions,
        detail: detailWith(actions: ['accept', 'decline', 'add_note']),
      );
      await openJob(t);
      await scrollTo(t, find.text('Accept job'));
      await t.tap(find.text('Accept job'));
      await t.pumpAndSettle();
      expect(
        find.textContaining('cannot move from IN_PROGRESS to ACCEPTED'),
        findsOneWidget,
      );
      expect(find.text('Job accepted.'), findsNothing);
      await unmountApp(t);
    });

    testWidgets('403 means no longer assigned', (t) async {
      final actions = FakeActionsRepository()
        ..error = const ApiException(
          status: 403,
          code: 'forbidden',
          message: 'Forbidden',
        );
      await pumpM3(
        t,
        actions: actions,
        detail: detailWith(actions: ['accept', 'decline', 'add_note']),
      );
      await openJob(t);
      await scrollTo(t, find.text('Accept job'));
      await t.tap(find.text('Accept job'));
      await t.pumpAndSettle();
      expect(find.textContaining('no longer assigned'), findsWidgets);
      await unmountApp(t);
    });

    testWidgets(
      'decline requires a reason (>= 5 chars), then returns to the inbox',
      (t) async {
        final rig = await pumpM3(
          t,
          detail: detailWith(actions: ['accept', 'decline', 'add_note']),
        );
        await openJob(t);
        await scrollTo(t, find.text('Decline job'));
        await t.tap(find.text('Decline job'));
        await t.pumpAndSettle();
        expect(find.text('Decline this job?'), findsOneWidget);
        await t.tap(find.text('Cancel'));
        await t.pumpAndSettle();
        expect(rig.actions.calls, isEmpty);

        await t.tap(find.text('Decline job'));
        await t.pumpAndSettle();
        await t.tap(find.widgetWithText(FilledButton, 'Decline job'));
        await t.pumpAndSettle();
        expect(find.textContaining('Reason is required'), findsOneWidget);
        await t.enterText(find.byType(TextField), 'abc');
        await t.tap(find.widgetWithText(FilledButton, 'Decline job'));
        await t.pumpAndSettle();
        expect(find.textContaining('Reason is required'), findsOneWidget);
        expect(rig.actions.calls, isEmpty);

        await t.enterText(find.byType(TextField), 'Sick leave today');
        await t.tap(find.widgetWithText(FilledButton, 'Decline job'));
        await t.pumpAndSettle();
        expect(rig.actions.calls, ['decline:Sick leave today']);
        expect(find.text('My jobs'), findsOneWidget); // back on the inbox
        expect(find.text('Job declined.'), findsOneWidget);
        await unmountApp(t);
      },
    );

    testWidgets('block and resume need a note and call the server', (t) async {
      final rig = await pumpM3(
        t,
        detail: detailWith(
          status: 'IN_PROGRESS',
          actions: ['block', 'complete', 'add_note'],
        ),
      );
      await openJob(t);
      await scrollTo(t, find.text('Report a blocker'));
      await t.tap(find.text('Report a blocker'));
      await t.pumpAndSettle();
      await t.tap(find.widgetWithText(FilledButton, 'Report blocker'));
      await t.pumpAndSettle();
      expect(find.textContaining('Reason is required'), findsOneWidget);
      await t.enterText(find.byType(TextField), 'Need a ladder');
      await t.tap(find.widgetWithText(FilledButton, 'Report blocker'));
      await t.pumpAndSettle();
      expect(rig.actions.calls, ['block:Need a ladder']);
      expect(find.text('Blocker reported.'), findsOneWidget);
      await unmountApp(t);
    });

    testWidgets('resume sends the resolution note', (t) async {
      final rig = await pumpM3(
        t,
        detail: detailWith(status: 'BLOCKED', actions: ['resume', 'add_note']),
      );
      await openJob(t);
      await scrollTo(t, find.text('Resume work'));
      await t.tap(find.text('Resume work'));
      await t.pumpAndSettle();
      await t.enterText(find.byType(TextField), 'Ladder arrived');
      await t.tap(find.widgetWithText(FilledButton, 'Resume work'));
      await t.pumpAndSettle();
      expect(rig.actions.calls, ['resume:Ladder arrived']);
      await unmountApp(t);
    });
  });

  group('start', () {
    testWidgets('blocked by estimate: disabled, server reason shown', (
      t,
    ) async {
      final rig = await pumpM3(
        t,
        item: itemWith(
          status: 'ACCEPTED',
          actions: ['decline', 'add_note'],
          blockedReason: 'Waiting for the requester to approve estimate v1.',
        ),
        detail: detailWith(
          status: 'ACCEPTED',
          actions: ['decline', 'add_note'],
        ),
      );
      await openJob(t);
      await scrollTo(t, find.text('Available actions'));
      expect(buttonEnabled(t, 'Start work'), isFalse);
      expect(
        find.textContaining(
          'Waiting for the requester to approve estimate v1.',
        ),
        findsWidgets,
      );
      await t.tap(find.text('Start work'), warnIfMissed: false);
      await t.pump();
      expect(rig.actions.calls, isEmpty);
      await unmountApp(t);
    });

    testWidgets('allowed start succeeds', (t) async {
      final rig = await pumpM3(
        t,
        detail: detailWith(
          status: 'ACCEPTED',
          actions: ['start', 'decline', 'add_note'],
        ),
      );
      await openJob(t);
      await scrollTo(t, find.text('Start work'));
      await t.tap(find.text('Start work'));
      await t.pumpAndSettle();
      expect(rig.actions.calls, ['start']);
      expect(find.text('Work started.'), findsOneWidget);
      await unmountApp(t);
    });

    testWidgets(
      '409 estimate_not_approved shows the server message, no success',
      (t) async {
        final actions = FakeActionsRepository()..error = _estimateErr;
        await pumpM3(
          t,
          actions: actions,
          detail: detailWith(
            status: 'ACCEPTED',
            actions: ['start', 'decline', 'add_note'],
          ),
        );
        await openJob(t);
        await scrollTo(t, find.text('Start work'));
        await t.tap(find.text('Start work'));
        await t.pumpAndSettle();
        expect(find.text('Could not start work'), findsOneWidget);
        expect(
          find.textContaining(
            'estimate must be approved before work can start',
          ),
          findsOneWidget,
        );
        expect(find.text('Work started.'), findsNothing);
        await unmountApp(t);
      },
    );
  });
}
