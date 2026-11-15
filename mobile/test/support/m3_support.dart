import 'dart:io';

import 'package:fixflow_tech/app.dart';
import 'package:fixflow_tech/core/db/database.dart';
import 'package:fixflow_tech/core/providers.dart';
import 'package:fixflow_tech/features/jobs/job_models.dart';
import 'package:fixflow_tech/features/jobs/jobs_providers.dart';
import 'package:fixflow_tech/features/outbox/outbox_providers.dart';
import 'package:fixflow_tech/features/outbox/outbox_repository.dart';
import 'package:fixflow_tech/features/profile/availability.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';

import 'fixtures.dart';
import 'harness.dart';
import 'm3_fakes.dart';
import 'outbox_support.dart';

class OfflineSwitch extends SimulateOffline {
  OfflineSwitch(this.initial);
  final bool initial;
  @override
  bool build() => initial;
}

/// Picker returning pre-made image files (no camera/gallery in tests).
class FakePicker implements PhotoPicker {
  FakePicker(this.files);
  final List<File> files;
  @override
  Future<List<PickedImage>> fromCamera() async => [
    for (final f in files)
      PickedImage(path: f.path, name: f.uri.pathSegments.last),
  ];
  @override
  Future<List<PickedImage>> fromGallery() => fromCamera();
}

class M3Rig {
  M3Rig({
    required this.repo,
    required this.actions,
    required this.notifications,
    required this.dir,
  });
  final FakeJobsRepository repo;
  final FakeActionsRepository actions;
  final FakeNotificationsRepository notifications;
  final Directory dir;
  late AppDatabase db;
}

JobDetail detailWith({
  String status = 'SCHEDULED',
  required List<String> actions,
  List<Map<String, dynamic>> materials = const [],
  Map<String, dynamic>? estimate,
}) {
  final j = jobJson()
    ..['status'] = status
    ..['allowed_actions'] = actions
    ..['materials'] = materials;
  if (estimate != null) j['estimate'] = estimate;
  return JobDetail.fromJson(j);
}

AssignmentItem itemWith({
  String status = 'SCHEDULED',
  required List<String> actions,
  String? blockedReason,
}) {
  final j = assignmentJson(status: status)
    ..['allowed_actions'] = actions
    ..['start_blocked_reason'] = blockedReason;
  return AssignmentItem.fromJson(j);
}

/// Pumps the whole app signed in as a technician and returns the rig.
Future<M3Rig> pumpM3(
  WidgetTester t, {
  required JobDetail detail,
  AssignmentItem? item,
  bool offline = false,
  FakeActionsRepository? actions,
  FakeNotificationsRepository? notifications,
  FakeTechnicianRepository? technician,
  List<File> pickerFiles = const [],
  List<Override> extra = const [],
}) async {
  // A tall phone so lazily-built list rows are all on screen.
  t.view.physicalSize = const Size(800, 2400);
  t.view.devicePixelRatio = 1;
  addTearDown(t.view.reset);
  final repo = FakeJobsRepository(
    pages: {
      AssignmentScope.upcoming: [item ?? assignment()],
    },
    detail: detail,
  );
  final fakeActions = actions ?? FakeActionsRepository();
  final fakeNotifs = notifications ?? FakeNotificationsRepository();
  final base = await baseOverrides(
    session: technicianSession(),
    repo: repo,
    notifications: fakeNotifs,
  );
  final dir = Directory.systemTemp.createTempSync('ff_m3_');
  addTearDown(() {
    if (dir.existsSync()) dir.deleteSync(recursive: true);
  });
  final rig = M3Rig(
    repo: repo,
    actions: fakeActions,
    notifications: fakeNotifs,
    dir: dir,
  );
  await t.pumpWidget(
    ProviderScope(
      overrides: [
        ...base,
        simulateOfflineProvider.overrideWith(() => OfflineSwitch(offline)),
        outboxRootProvider.overrideWithValue(() async => dir),
        jobActionsRepositoryProvider.overrideWithValue(fakeActions),
        photoPickerProvider.overrideWithValue(FakePicker(pickerFiles)),
        if (technician != null)
          technicianRepositoryProvider.overrideWithValue(technician),
        ...extra,
      ],
      child: Consumer(
        builder: (context, ref, _) {
          rig.db = ref.watch(appDatabaseProvider);
          return const FixFlowApp();
        },
      ),
    ),
  );
  await t.pumpAndSettle();
  return rig;
}

Future<void> openJob(WidgetTester t) async {
  await t.tap(find.text('REQ-7'));
  await t.pumpAndSettle();
}

Future<void> scrollTo(WidgetTester t, Finder f) async {
  await t.scrollUntilVisible(f, 300, scrollable: find.byType(Scrollable).first);
}

Future<void> unmountApp(WidgetTester t) async {
  await t.pumpWidget(const SizedBox());
  await t.pump(const Duration(milliseconds: 10));
}

File imageFile(Directory dir, String name) => writeImage(dir, name);

/// Enabled state of the button whose label is [label].
bool? buttonEnabled(WidgetTester t, String label) {
  final f = find.ancestor(
    of: find.text(label),
    matching: find.byWidgetPredicate((w) => w is ButtonStyleButton),
  );
  if (f.evaluate().isEmpty) return null;
  return (t.widget(f.first) as ButtonStyleButton).onPressed != null;
}

/// Lets real file IO (photo validation) finish, then settles the UI.
Future<void> settleIo(WidgetTester t) async {
  for (var i = 0; i < 30; i++) {
    await t.runAsync(
      () => Future<void>.delayed(const Duration(milliseconds: 10)),
    );
    await t.pump(const Duration(milliseconds: 10));
  }
  await t.pumpAndSettle();
}
