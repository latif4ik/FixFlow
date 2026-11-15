import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../theme/app_theme.dart';
import '../util/formatters.dart';

/// "Offline - showing data from 10:42" (MOB-03/MOB-04). Time in the org tz.
class StaleDataBanner extends StatelessWidget {
  const StaleDataBanner({super.key, required this.syncedAt, this.timezone});
  final DateTime? syncedAt;
  final String? timezone;

  @override
  Widget build(BuildContext context) {
    final at = syncedAt == null
        ? null
        : DateFormat('HH:mm').format(inZone(syncedAt!, timezone));
    return Container(
      width: double.infinity,
      color: AppColors.warningTint,
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      child: Row(
        children: [
          const Icon(Icons.history, size: 18, color: AppColors.warningText),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              at == null
                  ? 'Offline - showing saved data'
                  : 'Offline - showing data from $at',
              style: const TextStyle(
                color: AppColors.warningText,
                fontWeight: FontWeight.w600,
                fontSize: 13,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
