// Runs ON the Android emulator against the live backend (default
// http://10.0.2.2:8000). Writes demo data: run `reset-demo` afterwards.
//
//   flutter test integration_test -d <emulator id>
import 'dart:convert';
import 'dart:io';

import 'package:drift/native.dart';
import 'package:fixflow_tech/app.dart';
import 'package:fixflow_tech/core/auth/token_store.dart';
import 'package:fixflow_tech/core/config/app_config.dart';
import 'package:fixflow_tech/core/db/database.dart';
import 'package:fixflow_tech/core/providers.dart';
import 'package:fixflow_tech/core/util/formatters.dart';
import 'package:fixflow_tech/core/widgets/chips.dart';
import 'package:fixflow_tech/features/jobs/jobs_providers.dart';
import 'package:fixflow_tech/features/outbox/outbox_providers.dart';
import 'package:fixflow_tech/features/outbox/outbox_repository.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

const _email = 'technician1@northwind.demo';
const _password = 'demo1234';
const _jobTitle = 'Replace burnt-out corridor lights';
const _onlineNote = 'M3 integration note (online)';
const _offlineNote = 'M3 integration note (queued offline)';
const _completionNote =
    'Replaced all burnt-out corridor lights and tested the circuit.';

/// 1x1 PNG used as the "camera" result (the real picker cannot be driven).
final _png = base64Decode(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==',
);

class _FakePicker implements PhotoPicker {
  _FakePicker(this.file);
  final File file;
  @override
  Future<List<PickedImage>> fromCamera() async => [
    PickedImage(path: file.path, name: 'completion.png'),
  ];
  @override
  Future<List<PickedImage>> fromGallery() => fromCamera();
}

/// Minimal REST client to verify the server state independently of the UI.
class _Server {
  final base = AppConfig.defaultBaseUrl;
  late String token;
  late String orgId;

  /// GETs are retried: the verification client must not be flaky.
  Future<Object?> _call(String method, String path, [Object? body]) async {
    for (var attempt = 1; ; attempt++) {
      try {
        return await _once(method, path, body);
      } on IOException {
        final retryable = method == 'GET' || path == '/auth/login';
        if (!retryable || attempt >= 3) rethrow;
        await Future<void>.delayed(const Duration(milliseconds: 500));
      }
    }
  }

  Future<Object?> _once(String method, String path, [Object? body]) async {
    final c = HttpClient();
    try {
      final req = await c.openUrl(method, Uri.parse('$base/api/v1$path'));
      req.headers.contentType = ContentType.json;
      req.headers.set('Accept', 'application/json');
      if (path != '/auth/login') {
        req.headers.set('Authorization', 'Bearer $token');
        req.headers.set('X-Org-Id', orgId);
      }
      if (body != null) req.write(jsonEncode(body));
      final res = await req.close();
      final text = await utf8.decodeStream(res);
      if (res.statusCode >= 300) {
        throw StateError('$method $path -> ${res.statusCode}: $text');
      }
      return jsonDecode(text);
    } finally {
      c.close();
    }
  }

  Future<void> login() async {
    final j = await _call('POST', '/auth/login', {
      'email': _email,
      'password': _password,
    }) as Map;
    token = j['token'] as String;
    orgId =
        ((j['memberships'] as List).first as Map)['organization']['id']
            as String;
  }

  Future<Map> get(String path) async => await _call('GET', path) as Map;

  Future<String> requestIdByTitle(String title) async {
    for (final scope in ['upcoming', 'active', 'history']) {
      final page = await get('/me/assignments?scope=$scope&page_size=50');
      for (final i in page['items'] as List) {
        if (i['request']['title'] == title) return i['request']['id'] as String;
      }
    }
    throw StateError('job "$title" not found for $_email');
  }
}

Future<String> Function()? _diag;

/// Re-fetches the job: the emulator network can hiccup mid-run (heavily loaded
/// host), which leaves the screen on stale cached data until the next fetch.
void Function()? _nudge;

Future<String> _texts() async {
  final texts = find
      .byType(Text)
      .evaluate()
      .map((e) => (e.widget as Text).data)
      .whereType<String>()
      .take(40)
      .join(' | ');
  return '${await _diag?.call() ?? ''} :: $texts';
}

/// Pumps real time until [f] is found (live backend, real latency).
Future<void> waitFor(
  WidgetTester t,
  Finder f, {
  Duration timeout = const Duration(seconds: 40),
  String? why,
}) async {
  final end = DateTime.now().add(timeout);
  var lastNudge = DateTime.now();
  while (DateTime.now().isBefore(end)) {
    await t.pump(const Duration(milliseconds: 200));
    if (f.evaluate().isNotEmpty) return;
    if (DateTime.now().difference(lastNudge) > const Duration(seconds: 10)) {
      lastNudge = DateTime.now();
      _nudge?.call();
    }
  }
  fail('Timed out waiting for ${why ?? f}. On screen: ${await _texts()}');
}

Future<void> waitGone(
  WidgetTester t,
  Finder f, {
  Duration timeout = const Duration(seconds: 25),
}) async {
  final end = DateTime.now().add(timeout);
  while (DateTime.now().isBefore(end)) {
    await t.pump(const Duration(milliseconds: 200));
    if (f.evaluate().isEmpty) return;
  }
  fail('Timed out waiting for $f to disappear');
}

/// Marker for the host script that takes `adb screencap` screenshots.
Future<void> shot(WidgetTester t, String name) async {
  await t.pump(const Duration(milliseconds: 600));
  // ignore: avoid_print
  print('SHOT:$name');
  await Future<void>.delayed(const Duration(milliseconds: 2500));
  await t.pump();
}

/// Scrolls down until [f] is built, then brings the first match on screen.
Future<void> scrollTo(WidgetTester t, Finder f) async {
  final view = find.byType(Scrollable).first;
  for (var i = 0; i < 40 && f.evaluate().isEmpty; i++) {
    await t.drag(view, const Offset(0, -300));
    await t.pump(const Duration(milliseconds: 100));
  }
  expect(f, findsWidgets, reason: 'could not scroll to $f');
  await Scrollable.ensureVisible(t.element(f.first));
  await t.pump(const Duration(milliseconds: 200));
}

/// The status chip sits at the top of the (lazy) list: scroll up to it.
Future<void> expectStatusChip(WidgetTester t, String label) async {
  final chip = find.descendant(
    of: find.byType(StatusChip),
    matching: find.text(label),
  );
  for (var i = 0; i < 30 && chip.evaluate().isEmpty; i++) {
    await t.drag(find.byType(Scrollable).first, const Offset(0, 300));
    await t.pump(const Duration(milliseconds: 200));
  }
  expect(chip, findsWidgets);
}

Future<void> tapText(WidgetTester t, String text) async {
  await t.tap(find.text(text).first);
  await t.pump(const Duration(milliseconds: 300));
}

/// Taps [text] if it is (or can be scrolled to) on screen; silently does
/// nothing when it is not there (the action may already have been applied).
Future<void> tapIfPresent(WidgetTester t, String text) async {
  final f = find.text(text);
  final view = find.byType(Scrollable).first;
  for (var i = 0; i < 40 && f.evaluate().isEmpty; i++) {
    await t.drag(view, const Offset(0, -300));
    await t.pump(const Duration(milliseconds: 100));
  }
  if (f.evaluate().isEmpty) return;
  await Scrollable.ensureVisible(t.element(f.first));
  await t.pump(const Duration(milliseconds: 200));
  await t.tap(f.first);
}

/// Waits until the app considers itself online again (the emulator network
/// can hiccup on a loaded host; the app probes by itself every 15 s).
Future<void> waitOnline(WidgetTester t) async {
  final c = ProviderScope.containerOf(t.element(find.byType(FixFlowApp)));
  final end = DateTime.now().add(const Duration(seconds: 90));
  while (c.read(isOfflineProvider) && DateTime.now().isBefore(end)) {
    await t.pump(const Duration(milliseconds: 500));
  }
}

/// Runs [act] until [success] shows up. A failed attempt is allowed (the UI
/// then shows an error dialog / Retry button, as designed): dismiss it, wait
/// for connectivity and try again. Real server state is asserted by callers.
Future<void> until(
  WidgetTester t,
  Finder success,
  Future<void> Function() act, {
  required String why,
  int tries = 5,
}) async {
  for (var i = 0; i < tries; i++) {
    await act();
    final end = DateTime.now().add(const Duration(seconds: 40));
    while (DateTime.now().isBefore(end)) {
      await t.pump(const Duration(milliseconds: 200));
      if (success.evaluate().isNotEmpty) return;
      final ok = find.descendant(
        of: find.byType(AlertDialog),
        matching: find.text('OK'),
      );
      if (ok.evaluate().isNotEmpty) {
        // ignore: avoid_print
        print('NOTE attempt ${i + 1} for "$why" failed in the UI; retrying');
        await t.tap(ok);
        await t.pump(const Duration(milliseconds: 300));
        break;
      }
      // Inline failure state (complete form / material sheet): stop waiting.
      if (find.widgetWithText(FilledButton, 'Retry').evaluate().isNotEmpty) {
        break;
      }
    }
    await waitOnline(t);
  }
  fail('Timed out waiting for $why. On screen: ${await _texts()}');
}

Future<void> setOffline(WidgetTester t, bool offline) async {
  await t.tap(find.byTooltip('Profile'));
  await t.pumpAndSettle();
  final sw = find.widgetWithText(SwitchListTile, 'Simulate offline (debug)');
  await scrollTo(t, sw);
  if (t.widget<SwitchListTile>(sw).value != offline) {
    await t.tap(sw);
    await t.pump(const Duration(milliseconds: 500));
  }
  await t.pageBack();
  await t.pumpAndSettle();
}

void main() {
  final binding = IntegrationTestWidgetsFlutterBinding.ensureInitialized();
  binding.framePolicy = LiveTestWidgetsFlutterBindingFramePolicy.fullyLive;

  testWidgets('technician flow against the live backend', (t) async {
    initTimezones();
    SharedPreferences.setMockInitialValues({});
    final prefs = await SharedPreferences.getInstance();
    final tmp = await Directory.systemTemp.createTemp('ff_it_');
    final photo = File('${tmp.path}/completion.png')..writeAsBytesSync(_png);

    final server = _Server();
    await server.login();
    final requestId = await server.requestIdByTitle(_jobTitle);
    expect(
      (await server.get('/requests/$requestId'))['status'],
      'SCHEDULED',
      reason: 'run `reset-demo` first: the job must be SCHEDULED',
    );

    await t.pumpWidget(
      ProviderScope(
        overrides: [
          sharedPreferencesProvider.overrideWithValue(prefs),
          // Clean local state on every run.
          appDatabaseProvider.overrideWith((ref) {
            final db = AppDatabase(NativeDatabase.memory());
            ref.onDispose(db.close);
            return db;
          }),
          tokenStoreProvider.overrideWithValue(InMemoryTokenStore()),
          outboxRootProvider.overrideWithValue(() async => tmp),
          photoPickerProvider.overrideWithValue(_FakePicker(photo)),
        ],
        child: const FixFlowApp(),
      ),
    );
    _diag = () async {
      final c = ProviderScope.containerOf(t.element(find.byType(FixFlowApp)));
      final rows = c.read(appDatabaseProvider);
      return 'simulate=${c.read(simulateOfflineProvider)} '
          'offline=${c.read(isOfflineProvider)} '
          'reachable=${c.read(networkReachableProvider)} '
          'radio=${c.read(connectivityProvider)} '
          'cache=${(await rows.select(rows.cachedJobs).get()).map((r) => '${r.requestId.substring(0, 4)}:${r.scope}:item=${r.itemJson != null}:detail=${r.detailJson != null}').toList()}';
    };
    _nudge = () {
      final c = ProviderScope.containerOf(t.element(find.byType(FixFlowApp)));
      if (c.read(simulateOfflineProvider)) return;
      c.invalidate(jobDetailProvider(requestId));
    };
    await t.pump(const Duration(seconds: 1));

    // ---- sign in ----
    await waitFor(t, find.text('Sign in').first, why: 'sign-in screen');
    await shot(t, 'signin');
    await t.enterText(find.widgetWithText(TextFormField, 'Email'), _email);
    await t.enterText(
      find.widgetWithText(TextFormField, 'Password'),
      _password,
    );
    await t.tap(find.widgetWithText(FilledButton, 'Sign in'));
    await waitFor(t, find.text('My jobs'), why: 'inbox after sign-in');
    await waitFor(
      t,
      find.text(_jobTitle),
      why: 'seeded SCHEDULED job in the inbox',
    );
    await shot(t, 'inbox');

    // ---- open job, accept, start ----
    await t.tap(find.text(_jobTitle));
    await waitFor(t, find.text('Where'), why: 'job detail');
    await scrollTo(t, find.text('Accept job'));
    await shot(t, 'job_actions_scheduled');
    await until(
      t,
      find.text('Start work'),
      () => tapIfPresent(t, 'Accept job'),
      why: 'Start unlocked after accept',
    );
    await expectStatusChip(t, 'Accepted');
    expect((await server.get('/requests/$requestId'))['status'], 'ACCEPTED');

    await until(
      t,
      find.text('Mark complete'),
      () => tapIfPresent(t, 'Start work'),
      why: 'Complete unlocked after start',
    );
    await expectStatusChip(t, 'In progress');
    expect((await server.get('/requests/$requestId'))['status'], 'IN_PROGRESS');

    // ---- online note via the composer ----
    await scrollTo(t, find.text('New note'));
    await t.tap(find.text('New note'));
    await t.pumpAndSettle();
    await t.enterText(find.widgetWithText(TextField, 'Work note'), _onlineNote);
    await t.tap(find.text('Save note'));
    await scrollTo(t, find.text('New note'));
    await waitFor(t, find.text(_onlineNote), why: 'online note in the list');
    await waitGone(t, find.textContaining('Pending sync'));

    // ---- record a material (well-stocked item) ----
    await scrollTo(t, find.text('Record material'));
    await t.tap(find.text('Record material'));
    await waitFor(t, find.textContaining('CABLE-2.5'), why: 'inventory list');
    await t.enterText(
      find.widgetWithText(TextField, 'Search materials (code or name)'),
      'cable',
    );
    await t.pump(const Duration(milliseconds: 400));
    await t.tap(find.textContaining('CABLE-2.5'));
    await t.pump(const Duration(milliseconds: 400));
    await t.enterText(find.widgetWithText(TextField, 'Quantity (m)'), '1');
    await t.pump(const Duration(milliseconds: 300));
    final sheetButton = find.descendant(
      of: find.byType(BottomSheet),
      matching: find.byType(FilledButton),
    );
    await until(
      t,
      find.textContaining('Recorded 1.000 m of Copper cable'),
      () async {
        // "Record material", or "Retry" after a dropped connection.
        if (sheetButton.evaluate().isNotEmpty) await t.tap(sheetButton.first);
      },
      why: 'material success toast',
    );
    await waitFor(t, find.text('1.000 m'), why: 'material listed on the job');
    final mats =
        (await server.get('/requests/$requestId'))['materials'] as List;
    expect(mats, hasLength(1));
    expect(mats.single['quantity'], '1.000');

    // ---- offline: actions need a connection ----
    // Visit the Active tab online so it is in the offline cache.
    await t.pageBack();
    await t.pumpAndSettle();
    await tapText(t, 'Active');
    await waitFor(t, find.text(_jobTitle), why: 'job in the Active tab');
    await setOffline(t, true);
    await waitFor(
      t,
      find.textContaining("You're offline").first,
      why: 'offline banner',
    );
    await tapText(t, 'Active');
    await waitFor(t, find.text(_jobTitle), why: 'job in the cached Active tab');
    await t.tap(find.text(_jobTitle));
    await waitFor(t, find.text('Where'), why: 'job detail');
    await scrollTo(t, find.text('Mark complete'));
    expect(find.textContaining('Requires connection'), findsWidgets);
    final complete = find.ancestor(
      of: find.text('Mark complete'),
      matching: find.byWidgetPredicate((w) => w is ButtonStyleButton),
    );
    expect((t.widget(complete.first) as ButtonStyleButton).onPressed, isNull);
    await shot(t, 'offline_requires_connection');

    // ---- offline note => Pending sync ----
    await scrollTo(t, find.text('New note'));
    await t.tap(find.text('New note'));
    await t.pumpAndSettle();
    await t.enterText(
      find.widgetWithText(TextField, 'Work note'),
      _offlineNote,
    );
    await t.tap(find.text('Save note (queue offline)'));
    await scrollTo(t, find.text('New note'));
    await waitFor(
      t,
      find.textContaining('Pending sync'),
      why: 'Pending sync badge',
    );
    await shot(t, 'offline_pending_sync');
    var notes = (await server.get('/requests/$requestId'))['notes'] as List;
    expect(
      notes.where((n) => n['body'] == _offlineNote),
      isEmpty,
      reason: 'nothing may reach the server while simulated offline',
    );

    // ---- back online: synced exactly once ----
    await t.pageBack();
    await t.pumpAndSettle();
    await setOffline(t, false);
    await t.tap(find.text(_jobTitle));
    await waitFor(t, find.text('Where'), why: 'job detail');
    await scrollTo(t, find.text('New note'));
    await waitGone(
      t,
      find.textContaining('Pending sync'),
      timeout: const Duration(seconds: 45),
    );
    await waitFor(t, find.text(_offlineNote), why: 'synced note visible');
    notes = (await server.get('/requests/$requestId'))['notes'] as List;
    expect(
      notes.where((n) => n['body'] == _offlineNote),
      hasLength(1),
      reason: 'exactly one server note',
    );
    expect(notes.where((n) => n['body'] == _onlineNote), hasLength(1));
    expect(find.text(_offlineNote), findsOneWidget);

    // ---- notifications screen ----
    await t.pageBack();
    await t.pumpAndSettle();
    await t.tap(find.byTooltip('Notifications').first);
    await waitFor(t, find.text('New job assigned'), why: 'seeded notification');
    await shot(t, 'notifications');
    await t.pageBack();
    await t.pumpAndSettle();

    // ---- complete with a (injected) photo ----
    await tapText(t, 'Active');
    await waitFor(t, find.text(_jobTitle));
    await t.tap(find.text(_jobTitle));
    await waitFor(t, find.text('Where'), why: 'job detail');
    await scrollTo(t, find.text('Mark complete'));
    await t.tap(find.text('Mark complete'));
    await t.pumpAndSettle();
    await t.enterText(
      find.widgetWithText(TextField, 'Completion note'),
      _completionNote,
    );
    await t.tap(find.text('Gallery'));
    await waitFor(t, find.text('completion.png'), why: 'picked photo');
    await shot(t, 'complete_form');
    await until(t, find.text('Job completed.'), () async {
      final retry = find.widgetWithText(FilledButton, 'Retry');
      await t.tap(
        retry.evaluate().isNotEmpty
            ? retry
            : find.widgetWithText(FilledButton, 'Complete job'),
      );
    }, why: 'completion success');
    final done = await server.get('/requests/$requestId');
    expect(done['status'], 'COMPLETED');
    expect(
      (done['files'] as List).where((f) => f['purpose'] == 'COMPLETION'),
      hasLength(1),
    );
    await expectStatusChip(t, 'Completed');
    await shot(t, 'job_completed');

    // ---- profile / availability ----
    await t.pageBack();
    await t.pumpAndSettle();
    await t.tap(find.byTooltip('Profile'));
    await t.pumpAndSettle();
    await tapText(t, 'My availability');
    await waitFor(t, find.text('Weekly availability'));
    expect(find.text('09:00–18:00'), findsNWidgets(5));
    await shot(t, 'availability');

    await t.pumpWidget(const SizedBox());
    await t.pump(const Duration(milliseconds: 100));
  });
}
