import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/providers.dart';
import '../../core/widgets/state_views.dart';

/// Shown when the account has no TECHNICIAN membership.
class NoTechnicianAccessScreen extends ConsumerWidget {
  const NoTechnicianAccessScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) => Scaffold(
    appBar: AppBar(title: const Text('FixFlow Tech')),
    body: Padding(
      padding: const EdgeInsets.all(24),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          const Expanded(
            child: EmptyView(
              icon: Icons.block,
              title: 'Technician access required',
              message: 'This app is for technicians; use the web app.',
            ),
          ),
          OutlinedButton.icon(
            onPressed: () => ref.read(sessionProvider.notifier).signOut(),
            icon: const Icon(Icons.logout),
            label: const Text('Sign out'),
          ),
        ],
      ),
    ),
  );
}

/// Organization selector (also reachable from Profile to switch).
class OrgSelectScreen extends ConsumerWidget {
  const OrgSelectScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final session = ref.watch(sessionProvider);
    final memberships = session.technicianMemberships;
    return Scaffold(
      appBar: AppBar(
        title: const Text('Choose organization'),
        leading: session.selectedOrgId != null && context.canPop()
            ? const BackButton()
            : null,
        actions: [
          if (session.selectedOrgId == null)
            IconButton(
              tooltip: 'Sign out',
              icon: const Icon(Icons.logout),
              onPressed: () => ref.read(sessionProvider.notifier).signOut(),
            ),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          const Text('Select the organization whose jobs you want to see.'),
          const SizedBox(height: 12),
          for (final m in memberships)
            Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: Card(
                child: ListTile(
                  key: ValueKey('org-${m.organization.id}'),
                  leading: const Icon(Icons.business),
                  title: Text(m.organization.name),
                  subtitle: Text('Technician · ${m.organization.timezone}'),
                  trailing: m.organization.id == session.selectedOrgId
                      ? const Icon(Icons.check_circle)
                      : const Icon(Icons.chevron_right),
                  onTap: () async {
                    await ref
                        .read(sessionProvider.notifier)
                        .selectOrg(m.organization.id);
                    if (context.mounted) context.go('/inbox');
                  },
                ),
              ),
            ),
        ],
      ),
    );
  }
}
