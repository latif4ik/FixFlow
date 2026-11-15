import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/providers.dart';
import '../../core/widgets/section_card.dart';

class ProfileScreen extends ConsumerWidget {
  const ProfileScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final s = ref.watch(sessionProvider);
    final membership = s.selectedMembership;
    return Scaffold(
      appBar: AppBar(title: const Text('Profile')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          SectionCard(
            title: 'Account',
            children: [
              KeyValueRow('Name', s.user?.fullName ?? '-'),
              KeyValueRow('Email', s.user?.email ?? '-'),
            ],
          ),
          const SizedBox(height: 12),
          SectionCard(
            title: 'Organization',
            children: [
              KeyValueRow('Organization', membership?.organization.name ?? '-'),
              KeyValueRow('Role', membership?.role ?? '-'),
              KeyValueRow('Timezone', membership?.organization.timezone ?? '-'),
              if (s.technicianMemberships.length > 1) ...[
                const SizedBox(height: 8),
                OutlinedButton.icon(
                  onPressed: () => context.push('/select-org'),
                  icon: const Icon(Icons.swap_horiz),
                  label: const Text('Switch organization'),
                ),
              ],
            ],
          ),
          const SizedBox(height: 12),
          SectionCard(
            title: 'Server',
            children: [
              KeyValueRow('API address', ref.watch(serverUrlProvider)),
              const Text(
                'Change the address on the sign-in screen after signing out.',
                style: TextStyle(fontSize: 12),
              ),
              if (kDebugMode)
                SwitchListTile(
                  contentPadding: EdgeInsets.zero,
                  title: const Text('Simulate offline (debug)'),
                  value: ref.watch(simulateOfflineProvider),
                  onChanged: (v) =>
                      ref.read(simulateOfflineProvider.notifier).set(v),
                ),
            ],
          ),
          const SizedBox(height: 20),
          FilledButton.icon(
            onPressed: () => ref.read(sessionProvider.notifier).signOut(),
            icon: const Icon(Icons.logout),
            label: const Text('Sign out'),
          ),
        ],
      ),
    );
  }
}
