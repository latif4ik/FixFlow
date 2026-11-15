import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../providers.dart';
import '../theme/app_theme.dart';

/// MOB-08 helper for online-only actions (accept, transitions, estimate-
/// dependent start, inventory ...). While offline the child is built with
/// `enabled == false` (pass `onPressed: null`) and a visible explanation is
/// shown under it. Never fake the action locally.
class RequiresConnection extends ConsumerWidget {
  const RequiresConnection({
    super.key,
    required this.builder,
    this.reason = 'Requires connection',
  });

  final Widget Function(BuildContext context, bool enabled) builder;
  final String reason;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final offline = ref.watch(isOfflineProvider);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        builder(context, !offline),
        if (offline) RequiresConnectionLabel(text: reason),
      ],
    );
  }
}

/// The explanation line on its own ("Requires connection").
class RequiresConnectionLabel extends StatelessWidget {
  const RequiresConnectionLabel({super.key, this.text = 'Requires connection'});
  final String text;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(top: 4),
    child: Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        const Icon(Icons.cloud_off, size: 14, color: AppColors.muted),
        const SizedBox(width: 4),
        Flexible(
          child: Text(
            '$text - available when you are back online.',
            style: const TextStyle(fontSize: 12, color: AppColors.muted),
          ),
        ),
      ],
    ),
  );
}
