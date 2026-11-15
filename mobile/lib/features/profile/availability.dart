import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api/api_client.dart';
import '../../core/providers.dart';

class AvailabilitySlot {
  const AvailabilitySlot({
    required this.weekday,
    required this.start,
    required this.end,
  });

  /// 0 = Monday ... 6 = Sunday (backend convention).
  final int weekday;

  /// "HH:mm" (wall-clock time in the organization timezone).
  final String start;
  final String end;
}

class TimeOff {
  const TimeOff({required this.start, required this.end, this.reason});
  final DateTime start;
  final DateTime end;
  final String? reason;
}

/// GET /technicians/me (read-only view).
class TechnicianProfile {
  const TechnicianProfile({
    required this.skills,
    required this.availability,
    required this.timeOff,
  });

  factory TechnicianProfile.fromJson(Map<String, dynamic> j) {
    String hm(Object? v) {
      final s = (v ?? '').toString();
      return s.length >= 5 ? s.substring(0, 5) : s;
    }

    final off = <TimeOff>[];
    for (final t in (j['time_off'] as List? ?? const [])) {
      final s = DateTime.tryParse((t['start_at'] ?? '').toString());
      final e = DateTime.tryParse((t['end_at'] ?? '').toString());
      if (s != null && e != null) {
        off.add(TimeOff(start: s, end: e, reason: t['reason'] as String?));
      }
    }
    return TechnicianProfile(
      skills: [
        for (final s in (j['skills'] as List? ?? const []))
          (s['name'] ?? '').toString(),
      ],
      availability: [
        for (final a in (j['availability'] as List? ?? const []))
          AvailabilitySlot(
            weekday: (a['weekday'] as num).toInt(),
            start: hm(a['start_time']),
            end: hm(a['end_time']),
          ),
      ],
      timeOff: off,
    );
  }

  final List<String> skills;
  final List<AvailabilitySlot> availability;
  final List<TimeOff> timeOff;
}

abstract class TechnicianRepository {
  Future<TechnicianProfile> me();
}

class ApiTechnicianRepository implements TechnicianRepository {
  ApiTechnicianRepository(this._api);
  final ApiClient _api;

  @override
  Future<TechnicianProfile> me() async =>
      TechnicianProfile.fromJson(await _api.getJson('/technicians/me'));
}

final technicianRepositoryProvider = Provider<TechnicianRepository>(
  (ref) => ApiTechnicianRepository(ref.watch(apiClientProvider)),
);

final technicianProfileProvider = FutureProvider.autoDispose<TechnicianProfile>(
  (ref) {
    ref.watch(selectedOrgIdProvider);
    return ref.read(technicianRepositoryProvider).me();
  },
);
