import 'dart:io';

import 'package:dio/dio.dart';
import 'package:fixflow_tech/core/api/api_client.dart';
import 'package:fixflow_tech/core/api/api_exception.dart';
import 'package:fixflow_tech/core/util/formatters.dart';
import 'package:fixflow_tech/features/jobs/job_actions_repository.dart';
import 'package:fixflow_tech/features/jobs/job_models.dart';
import 'package:fixflow_tech/features/jobs/job_materials.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/fake_adapter.dart';
import 'support/m3_fakes.dart';
import 'support/m3_support.dart';

const _note = 'Replaced all burnt-out lamps and tested the circuit.';

JobDetail detailInProgress() => detailWith(
  status: 'IN_PROGRESS',
  actions: ['block', 'complete', 'add_note'],
);

Future<void> openComplete(WidgetTester t) async {
  await openJob(t);
  await scrollTo(t, find.text('Mark complete'));
  await t.tap(find.text('Mark complete'));
  await t.pumpAndSettle();
  expect(find.textContaining('Completion note'), findsWidgets);
}

Finder sheetButton(String label) => find.descendant(
  of: find.byType(RecordMaterialSheet),
  matching: find.widgetWithText(FilledButton, label),
);

void main() {
  setUpAll(initTimezones);

  group('complete job', () {
    testWidgets('validation: short note and missing photo block submission', (
      t,
    ) async {
      final rig = await pumpM3(t, detail: detailInProgress());
      await openComplete(t);
      expect(find.text('0/20 minimum'), findsOneWidget);

      await t.tap(find.text('Complete job'));
      await t.pumpAndSettle();
      expect(find.textContaining('at least 20 characters'), findsOneWidget);
      expect(find.text('Add at least one completion photo.'), findsOneWidget);

      await t.enterText(find.byType(TextField), 'too short');
      await t.pump();
      expect(find.text('9/20 minimum'), findsOneWidget); // live counter
      await t.tap(find.text('Complete job'));
      await t.pumpAndSettle();
      expect(find.textContaining('(9/20)'), findsOneWidget);

      // long enough note but still no photo
      await t.enterText(find.byType(TextField), _note);
      await t.tap(find.text('Complete job'));
      await t.pumpAndSettle();
      expect(find.textContaining('at least 20 characters'), findsNothing);
      expect(find.text('Add at least one completion photo.'), findsOneWidget);
      expect(rig.actions.calls, isEmpty); // nothing reached the server
      await unmountApp(t);
    });

    testWidgets(
      'success: uploads COMPLETION photo, posts complete, refreshes',
      (t) async {
        final dir = Directory.systemTemp.createTempSync('ff_img_');
        final rig = await pumpM3(
          t,
          detail: detailInProgress(),
          pickerFiles: [imageFile(dir, 'work.png')],
        );
        await openComplete(t);
        await t.enterText(find.byType(TextField), _note);
        await t.tap(find.text('Gallery'));
        await settleIo(t);
        expect(find.text('work.png'), findsOneWidget);
        expect(find.text('Ready to upload'), findsOneWidget);
        final before = rig.repo.detailCalls;
        await t.tap(find.text('Complete job'));
        await t.pumpAndSettle();

        expect(rig.actions.calls, ['upload', 'complete:$_note']);
        expect(rig.actions.uploads.single.commandId, isNotEmpty);
        expect(rig.repo.detailCalls, greaterThan(before));
        expect(find.text('Job completed.'), findsOneWidget);
        expect(find.textContaining('Complete REQ-10'), findsNothing); // popped
        await unmountApp(t);
      },
    );

    testWidgets('server rejects completion: message, photos stay, no success; '
        'retry does not re-upload', (t) async {
      final dir = Directory.systemTemp.createTempSync('ff_img_');
      final actions = FakeActionsRepository()
        ..completeError = const ApiException(
          status: 422,
          code: 'validation_error',
          message: 'A completion image is required.',
          details: [
            {'field': 'completion_images', 'message': 'Upload at least one.'},
          ],
        );
      final rig = await pumpM3(
        t,
        actions: actions,
        detail: detailInProgress(),
        pickerFiles: [imageFile(dir, 'work.png')],
      );
      await openComplete(t);
      await t.enterText(find.byType(TextField), _note);
      await t.tap(find.text('Camera'));
      await settleIo(t);
      await t.tap(find.text('Complete job'));
      await t.pumpAndSettle();

      expect(find.textContaining('NOT completed'), findsOneWidget);
      expect(
        find.textContaining('A completion image is required.'),
        findsOneWidget,
      );
      expect(find.textContaining('already attached'), findsOneWidget);
      expect(find.text('Uploaded'), findsOneWidget);
      expect(find.text('Job completed.'), findsNothing);
      expect(find.text('Retry'), findsOneWidget);

      actions.completeError = null;
      await t.tap(find.text('Retry'));
      await t.pumpAndSettle();
      expect(rig.actions.uploads, hasLength(1)); // not uploaded again
      expect(
        rig.actions.calls.where((c) => c.startsWith('complete')),
        hasLength(2),
      );
      expect(find.text('Job completed.'), findsOneWidget);
      await unmountApp(t);
    });

    testWidgets('409 invalid_transition on complete shows the message only', (
      t,
    ) async {
      final dir = Directory.systemTemp.createTempSync('ff_img_');
      final actions = FakeActionsRepository()
        ..completeError = const ApiException(
          status: 409,
          code: 'invalid_transition',
          message: 'A request cannot move from BLOCKED to COMPLETED.',
        );
      await pumpM3(
        t,
        actions: actions,
        detail: detailInProgress(),
        pickerFiles: [imageFile(dir, 'a.png')],
      );
      await openComplete(t);
      await t.enterText(find.byType(TextField), _note);
      await t.tap(find.text('Gallery'));
      await settleIo(t);
      await t.tap(find.text('Complete job'));
      await t.pumpAndSettle();
      expect(
        find.textContaining('cannot move from BLOCKED to COMPLETED'),
        findsOneWidget,
      );
      expect(find.text('Job completed.'), findsNothing);
      await unmountApp(t);
    });

    testWidgets('failed photo upload keeps its command id for the retry', (
      t,
    ) async {
      final dir = Directory.systemTemp.createTempSync('ff_img_');
      final actions = FakeActionsRepository()
        ..uploadError = const NetworkException('x', true);
      final rig = await pumpM3(
        t,
        actions: actions,
        detail: detailInProgress(),
        pickerFiles: [imageFile(dir, 'a.png')],
      );
      await openComplete(t);
      await t.enterText(find.byType(TextField), _note);
      await t.tap(find.text('Gallery'));
      await settleIo(t);
      await t.tap(find.text('Complete job'));
      await t.pumpAndSettle();
      expect(find.textContaining('Upload failed'), findsOneWidget);
      expect(find.textContaining('job was NOT'), findsOneWidget);
      expect(rig.actions.calls, ['upload']); // complete never attempted

      actions.uploadError = null;
      await t.tap(find.text('Retry'));
      await t.pumpAndSettle();
      expect(rig.actions.uploads, hasLength(2));
      expect(
        rig.actions.uploads[0].commandId,
        rig.actions.uploads[1].commandId,
      );
      expect(find.text('Job completed.'), findsOneWidget);
      await unmountApp(t);
    });

    testWidgets('non-image file is rejected before any upload', (t) async {
      final dir = Directory.systemTemp.createTempSync('ff_img_');
      final bad = File('${dir.path}/notes.png')
        ..writeAsStringSync('not an image');
      final rig = await pumpM3(
        t,
        detail: detailInProgress(),
        pickerFiles: [bad],
      );
      await openComplete(t);
      await t.tap(find.text('Gallery'));
      await settleIo(t);
      expect(find.textContaining('not a JPEG, PNG or WebP'), findsOneWidget);
      expect(find.text('notes.png'), findsNothing);
      expect(rig.actions.calls, isEmpty);
      await unmountApp(t);
    });

    testWidgets('offline: completing is disabled with an explanation', (
      t,
    ) async {
      await pumpM3(t, offline: true, detail: detailInProgress());
      await openJob(t);
      await scrollTo(t, find.text('Mark complete'));
      expect(buttonEnabled(t, 'Mark complete'), isFalse);
      expect(find.textContaining('Requires connection'), findsWidgets);
      await unmountApp(t);
    });
  });

  group('materials', () {
    test('validateQuantity', () {
      expect(validateQuantity(''), isNotNull);
      expect(validateQuantity('abc'), isNotNull);
      expect(validateQuantity('0'), 'Quantity must be greater than 0.');
      expect(validateQuantity('0.000'), isNotNull);
      expect(validateQuantity('-1'), isNotNull);
      expect(validateQuantity('1.2345'), isNotNull); // > 3 decimals
      expect(validateQuantity('1e3'), isNotNull);
      expect(validateQuantity('2'), isNull);
      expect(validateQuantity('0.5'), isNull);
      expect(validateQuantity('1,25'), isNull);
      expect(validateQuantity(' 3.125 '), isNull);
    });

    Future<void> openSheet(WidgetTester t) async {
      await openJob(t);
      await scrollTo(t, find.text('Record material'));
      await t.tap(find.text('Record material'));
      await t.pumpAndSettle();
    }

    testWidgets('only offered on an IN_PROGRESS job; offline disables it', (
      t,
    ) async {
      await pumpM3(
        t,
        detail: detailWith(
          status: 'ACCEPTED',
          actions: ['start', 'decline', 'add_note'],
        ),
      );
      await openJob(t);
      expect(find.text('Record material'), findsNothing);
      await unmountApp(t);
    });

    testWidgets('offline: Record material is disabled and explained', (
      t,
    ) async {
      await pumpM3(t, offline: true, detail: detailInProgress());
      await openJob(t);
      await scrollTo(t, find.text('Record material'));
      expect(buttonEnabled(t, 'Record material'), isFalse);
      expect(find.textContaining('Requires connection'), findsWidgets);
      await unmountApp(t);
    });

    testWidgets('lists existing usage, searches, validates quantity, records', (
      t,
    ) async {
      final rig = await pumpM3(
        t,
        detail: detailWith(
          status: 'IN_PROGRESS',
          actions: ['block', 'complete', 'add_note'],
          materials: [
            {
              'id': 'u0',
              'item': {
                'id': 'i2',
                'code': 'BREAKER-16A',
                'name': 'Circuit breaker 16 A',
                'unit': 'pcs',
              },
              'quantity': '1.500',
              'total_cost_minor': 31500,
              'currency': 'KGS',
            },
          ],
        ),
      );
      await openJob(t);
      await scrollTo(t, find.text('Record material'));
      expect(find.text('Circuit breaker 16 A'), findsOneWidget);
      expect(find.text('1.500 pcs'), findsOneWidget);
      await t.tap(find.text('Record material'));
      await t.pumpAndSettle();

      // search filters by code or name
      expect(find.textContaining('CABLE-2.5'), findsOneWidget);
      expect(find.textContaining('BREAKER-16A'), findsOneWidget);
      await t.enterText(find.byType(TextField).first, 'cable');
      await t.pumpAndSettle();
      expect(find.textContaining('BREAKER-16A · Circuit'), findsNothing);
      await t.tap(find.textContaining('CABLE-2.5'));
      await t.pumpAndSettle();
      expect(find.text('In stock: 293.500 m'), findsOneWidget);

      // invalid quantities never reach the server
      for (final bad in ['', '0', '1.2345', 'abc']) {
        await t.enterText(find.byType(TextField).last, bad);
        await t.tap(sheetButton('Record material'));
        await t.pumpAndSettle();
      }
      expect(rig.actions.consumes, isEmpty);
      expect(
        find.textContaining('greater than 0'),
        findsNothing,
      ); // last was 'abc'
      expect(find.textContaining('up to 3 decimals'), findsOneWidget);

      await t.enterText(find.byType(TextField).last, '2,5');
      await t.tap(sheetButton('Record material'));
      await t.pumpAndSettle();
      expect(rig.actions.consumes, hasLength(1));
      expect(rig.actions.consumes.single.quantity, '2.5');
      expect(rig.actions.consumes.single.itemId, 'i1');
      expect(
        find.textContaining('Recorded 2.5 m of Copper cable'),
        findsOneWidget,
      );
      await unmountApp(t);
    });

    testWidgets('timeout then retry reuses the SAME client_command_id', (
      t,
    ) async {
      final actions = FakeActionsRepository()
        ..consumeError = const NetworkException('slow', true);
      final rig = await pumpM3(t, actions: actions, detail: detailInProgress());
      await openSheet(t);
      await t.tap(find.textContaining('CABLE-2.5'));
      await t.pumpAndSettle();
      await t.enterText(find.byType(TextField).last, '1');
      await t.tap(sheetButton('Record material'));
      await t.pumpAndSettle();

      expect(find.textContaining('connection dropped'), findsOneWidget);
      expect(find.textContaining('Recorded'), findsNothing);
      // inputs are locked so the retry has the identical payload
      expect(t.widget<TextField>(find.byType(TextField).last).enabled, isFalse);

      actions.consumeError = null;
      await t.tap(sheetButton('Retry'));
      await t.pumpAndSettle();
      expect(rig.actions.consumes, hasLength(2));
      expect(
        rig.actions.consumes[0].commandId,
        rig.actions.consumes[1].commandId,
      );
      expect(
        rig.actions.consumes[0].quantity,
        rig.actions.consumes[1].quantity,
      );
      expect(find.textContaining('Recorded 1 m'), findsOneWidget);
      await unmountApp(t);
    });

    testWidgets('insufficient_stock shows the available quantity, no success', (
      t,
    ) async {
      final actions = FakeActionsRepository()
        ..consumeError = const ApiException(
          status: 409,
          code: 'insufficient_stock',
          message: 'Not enough stock for this item.',
          details: {'available': '20.500', 'requested': '99999'},
        );
      final rig = await pumpM3(t, actions: actions, detail: detailInProgress());
      await openSheet(t);
      await t.tap(find.textContaining('BREAKER-16A'));
      await t.pumpAndSettle();
      await t.enterText(find.byType(TextField).last, '99999');
      await t.tap(sheetButton('Record material'));
      await t.pumpAndSettle();
      expect(
        find.textContaining(
          'Not enough stock for Circuit breaker 16 A. Available: 20.500 pcs.',
        ),
        findsOneWidget,
      );
      expect(find.textContaining('Recorded'), findsNothing);
      // a definitive rejection allows a fresh attempt with a new key
      actions.consumeError = null;
      await t.enterText(find.byType(TextField).last, '1');
      await t.tap(sheetButton('Record material'));
      await t.pumpAndSettle();
      expect(rig.actions.consumes, hasLength(2));
      expect(
        rig.actions.consumes[0].commandId == rig.actions.consumes[1].commandId,
        isFalse,
      );
      await unmountApp(t);
    });
  });

  group('wire contract (ApiJobActionsRepository)', () {
    ApiJobActionsRepository repoWith(FakeAdapter a) => ApiJobActionsRepository(
      ApiClient(
        ApiClient.buildDio(
          baseUrl: 'http://fake',
          authContext: () => (token: 't', orgId: 'o1'),
          adapter: a,
        ),
      ),
    );

    test(
      'consume sends client_command_id/item_id/quantity; 200 replay ok',
      () async {
        final a = FakeAdapter(
          (o) => FakeAdapter.json(200, {
            'id': 'u',
            'item': {'code': 'C', 'name': 'N', 'unit': 'm'},
            'quantity': '1.500',
            'client_command_id': 'cid',
          }),
        );
        final r = await repoWith(a).consumeMaterial(
          'r1',
          commandId: 'cid',
          itemId: 'i1',
          quantity: '1.5',
        );
        expect(a.requests.single.path, endsWith('/requests/r1/materials'));
        expect(a.requests.single.data, {
          'client_command_id': 'cid',
          'item_id': 'i1',
          'quantity': '1.5',
        });
        expect(r.quantity, '1.500');
      },
    );

    test('decline/block/resume/complete bodies', () async {
      final a = FakeAdapter((o) => FakeAdapter.json(200, {'id': 'r1'}));
      final r = repoWith(a);
      await r.decline('r1', 'sick');
      await r.block('r1', 'ladder');
      await r.resume('r1', 'ok');
      await r.complete('r1', 'done');
      await r.accept('r1');
      await r.start('r1');
      expect(a.requests.map((o) => o.path.split('/api/v1').last), [
        '/requests/r1/decline',
        '/requests/r1/block',
        '/requests/r1/resume',
        '/requests/r1/complete',
        '/requests/r1/accept',
        '/requests/r1/start',
      ]);
      expect(a.requests[0].data, {'reason': 'sick'});
      expect(a.requests[1].data, {'reason': 'ladder'});
      expect(a.requests[2].data, {'note': 'ok'});
      expect(a.requests[3].data, {'note': 'done'});
    });

    test('completion upload is multipart purpose=COMPLETION with idempotency fields', () async {
      final dir = Directory.systemTemp.createTempSync('ff_img_');
      final f = imageFile(dir, 'p.png');
      final a = FakeAdapter((o) => FakeAdapter.json(201, {'id': 'file-1'}));
      final id = await repoWith(
        a,
      ).uploadCompletionPhoto('r1', path: f.path, commandId: 'cmd', index: 0);
      expect(id, 'file-1');
      final fd = a.requests.single.data as FormData;
      final fields = {for (final e in fd.fields) e.key: e.value};
      expect(fields['purpose'], 'COMPLETION');
      expect(fields['client_command_id'], 'cmd');
      expect(fields['client_index'], '0');
      expect(fd.files.single.value.contentType.toString(), 'image/png');
    });

    test('server error envelope keeps code and details', () async {
      final a = FakeAdapter(
        (o) => FakeAdapter.json(409, {
          'error': {
            'code': 'insufficient_stock',
            'message': 'Not enough stock for this item.',
            'details': {'available': '20.500'},
          },
        }),
      );
      await expectLater(
        repoWith(a)
            .consumeMaterial('r1', commandId: 'c', itemId: 'i', quantity: '9'),
        throwsA(
          isA<ApiException>()
              .having((e) => e.code, 'code', 'insufficient_stock')
              .having(
                (e) => (e.details as Map)['available'],
                'available',
                '20.500',
              ),
        ),
      );
    });
  });
}
