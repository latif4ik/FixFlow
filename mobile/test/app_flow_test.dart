import 'package:fixflow_tech/app.dart';
import 'package:fixflow_tech/core/api/api_exception.dart';
import 'package:fixflow_tech/core/util/formatters.dart';
import 'package:fixflow_tech/features/jobs/job_models.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';

import 'support/fixtures.dart';
import 'support/harness.dart';

Future<void> pumpApp(
  WidgetTester t,
  FakeJobsRepository repo, {
  List<Override> extra = const [],
}) async {
  final overrides = await baseOverrides(
    session: technicianSession(),
    repo: repo,
  );
  await t.pumpWidget(
    ProviderScope(
      overrides: [...overrides, ...extra],
      child: const FixFlowApp(),
    ),
  );
  await t.pumpAndSettle();
}

void main() {
  setUpAll(initTimezones);

  testWidgets(
    'inbox shows assignment cards with REQ id, status and org-tz window',
    (t) async {
      final repo = FakeJobsRepository(
        pages: {
          AssignmentScope.upcoming: [
            assignment(),
            assignment(id: 'r2', display: 'REQ-34'),
          ],
        },
      );
      await pumpApp(t, repo);
      expect(find.text('REQ-7'), findsOneWidget);
      expect(find.text('REQ-34'), findsOneWidget);
      expect(
        find.text('Scheduled'),
        findsNWidgets(2),
      ); // status text, not color only
      expect(find.text('High priority'), findsNWidgets(2));
      expect(
        find.text('Mon 16 Nov, 10:00–11:00'),
        findsNWidgets(2),
      ); // 04:00Z in Bishkek
      expect(find.textContaining('Northwind HQ Tower'), findsNWidgets(2));
      expect(find.textContaining('12 Chuy Ave'), findsNWidgets(2));
      expect(find.text('Upcoming'), findsOneWidget);
      expect(find.text('Org o1'), findsOneWidget);
    },
  );

  testWidgets('empty tab shows the empty state', (t) async {
    await pumpApp(t, FakeJobsRepository());
    expect(find.text('No upcoming jobs'), findsOneWidget);
    await t.tap(find.text('History'));
    await t.pumpAndSettle();
    expect(find.text('No history jobs'), findsOneWidget);
  });

  testWidgets('network failure shows offline state with retry', (t) async {
    await pumpApp(t, FakeJobsRepository(listError: const NetworkException()));
    expect(find.text("You're offline"), findsWidgets);
    expect(find.text('Try again'), findsOneWidget);
  });

  testWidgets(
    'tapping a card opens job detail with address, asset, priority, actions',
    (t) async {
      final repo = FakeJobsRepository(
        pages: {
          AssignmentScope.upcoming: [assignment()],
        },
        detail: JobDetail.fromJson(jobJson()),
      );
      await pumpApp(t, repo);
      await t.tap(find.text('REQ-7'));
      await t.pumpAndSettle();
      expect(find.text('Repair the stuck service door'), findsOneWidget);
      expect(find.text('88 Sovetskaya St, Bishkek'), findsOneWidget);
      expect(find.text('Riverside Mall'), findsOneWidget);
      expect(find.text('AC-12 · Rooftop unit'), findsOneWidget);
      expect(find.text('High priority'), findsOneWidget);
      expect(find.text('Blocked'), findsWidgets);
      expect(find.text('Mon 16 Nov, 14:00–15:00'), findsOneWidget); // 08:00Z
      expect(find.text('Check in at the front desk.'), findsOneWidget);
      expect(find.text('SLA at risk'), findsOneWidget);
      await t.scrollUntilVisible(find.text('Available actions'), 400);
      expect(find.text('Resume work'), findsOneWidget);
      expect(find.text('Add note'), findsOneWidget);
      expect(find.text('1 200.00 KGS'), findsOneWidget); // estimate total
    },
  );

  testWidgets('404 on detail says the technician is no longer assigned', (
    t,
  ) async {
    final repo = FakeJobsRepository(
      pages: {
        AssignmentScope.upcoming: [assignment()],
      },
      detailError: apiError(404),
    );
    await pumpApp(t, repo);
    await t.tap(find.text('REQ-7'));
    await t.pumpAndSettle();
    expect(
      find.text('You are no longer assigned to this job.'),
      findsOneWidget,
    );
    expect(find.text('Back to my jobs'), findsOneWidget);
  });

  testWidgets('403 on detail shows permission denied', (t) async {
    final repo = FakeJobsRepository(
      pages: {
        AssignmentScope.upcoming: [assignment()],
      },
      detailError: apiError(403, 'Not allowed.'),
    );
    await pumpApp(t, repo);
    await t.tap(find.text('REQ-7'));
    await t.pumpAndSettle();
    expect(find.text('No access'), findsOneWidget);
    expect(find.text('Not allowed.'), findsOneWidget);
  });
}
