import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'core/config/app_config.dart';
import 'core/providers.dart';
import 'core/theme/app_theme.dart';
import 'core/widgets/offline_banner.dart';
import 'core/widgets/state_views.dart';
import 'features/auth/sign_in_screen.dart';
import 'features/jobs/inbox_screen.dart';
import 'features/jobs/job_detail_screen.dart';
import 'features/jobs/job_models.dart';
import 'features/org/org_screens.dart';
import 'features/outbox/outbox_providers.dart';
import 'features/outbox/outbox_screen.dart';
import 'features/profile/profile_screen.dart';

/// Pure redirect rule (unit-tested). Returns null to stay on [location].
String? redirectFor(SessionState s, String location) {
  switch (s.status) {
    case SessionStatus.bootstrapping:
      return location == '/splash' ? null : '/splash';
    case SessionStatus.signedOut:
    case SessionStatus.expired:
      return location == '/sign-in' ? null : '/sign-in';
    case SessionStatus.signedIn:
      switch (s.route) {
        case OrgRoute.noTechnicianAccess:
          return location == '/no-access' ? null : '/no-access';
        case OrgRoute.selectOrg:
          return location == '/select-org' ? null : '/select-org';
        case OrgRoute.inbox:
          const auth = {'/sign-in', '/splash', '/no-access'};
          if (auth.contains(location)) return '/inbox';
          if (location == '/select-org' && s.technicianMemberships.length < 2) {
            return '/inbox';
          }
          return null;
      }
  }
}

final routerProvider = Provider<GoRouter>((ref) {
  final refresh = ValueNotifier<int>(0);
  ref.listen(sessionProvider, (_, _) => refresh.value++);
  ref.onDispose(refresh.dispose);
  final router = GoRouter(
    initialLocation: '/splash',
    refreshListenable: refresh,
    redirect: (context, state) =>
        redirectFor(ref.read(sessionProvider), state.matchedLocation),
    routes: [
      GoRoute(
        path: '/splash',
        builder: (_, _) => const Scaffold(body: LoadingView()),
      ),
      GoRoute(path: '/sign-in', builder: (_, _) => const SignInScreen()),
      GoRoute(
        path: '/no-access',
        builder: (_, _) => const NoTechnicianAccessScreen(),
      ),
      GoRoute(path: '/select-org', builder: (_, _) => const OrgSelectScreen()),
      GoRoute(path: '/inbox', builder: (_, _) => const InboxScreen()),
      GoRoute(
        path: '/jobs/:id',
        builder: (_, state) => JobDetailScreen(
          requestId: state.pathParameters['id']!,
          hint: state.extra is AssignmentItem
              ? state.extra! as AssignmentItem
              : null,
        ),
      ),
      GoRoute(path: '/outbox', builder: (_, _) => const OutboxScreen()),
      GoRoute(path: '/profile', builder: (_, _) => const ProfileScreen()),
    ],
  );
  ref.onDispose(router.dispose);
  return router;
});

class FixFlowApp extends ConsumerWidget {
  const FixFlowApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    // Starts the outbox sync engine (app start, reconnect, timer).
    ref.watch(syncControllerProvider);
    return MaterialApp.router(
      title: AppConfig.appName,
      theme: buildAppTheme(),
      routerConfig: ref.watch(routerProvider),
      debugShowCheckedModeBanner: false,
      builder: (context, child) => Column(
        children: [
          const OfflineBanner(),
          Expanded(child: child ?? const SizedBox.shrink()),
        ],
      ),
    );
  }
}
