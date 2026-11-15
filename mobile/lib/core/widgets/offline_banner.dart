import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../providers.dart';
import '../theme/app_theme.dart';

/// Persistent banner shown at the top of every screen while offline.
class OfflineBanner extends ConsumerWidget {
  const OfflineBanner({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final offline = ref.watch(isOfflineProvider);
    if (!offline) return const SizedBox.shrink();
    return Material(
      color: AppColors.warningTint,
      child: SafeArea(
        bottom: false,
        child: Container(
          width: double.infinity,
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
          child: Row(
            children: [
              const Icon(
                Icons.cloud_off,
                size: 18,
                color: AppColors.warningText,
              ),
              const SizedBox(width: 8),
              const Expanded(
                child: Text(
                  "You're offline. Showing the last loaded data.",
                  style: TextStyle(
                    color: AppColors.warningText,
                    fontWeight: FontWeight.w600,
                    fontSize: 13,
                  ),
                ),
              ),
              // The server stopped answering although the device has a
              // network: let the user re-check instead of waiting.
              if (!ref.watch(simulateOfflineProvider))
                TextButton(
                  onPressed: () => probeServer(ref),
                  child: const Text('Retry'),
                ),
            ],
          ),
        ),
      ),
    );
  }
}
