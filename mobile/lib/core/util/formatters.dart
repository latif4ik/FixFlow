import 'package:intl/intl.dart';
import 'package:timezone/data/latest.dart' as tzdata;
import 'package:timezone/timezone.dart' as tz;

bool _tzReady = false;

/// Loads the bundled IANA database once (safe to call repeatedly).
void initTimezones() {
  if (_tzReady) return;
  tzdata.initializeTimeZones();
  _tzReady = true;
}

tz.Location _location(String? name) {
  initTimezones();
  try {
    return tz.getLocation(name ?? 'UTC');
  } catch (_) {
    return tz.UTC;
  }
}

/// Converts a UTC instant to wall-clock time in the given IANA zone.
tz.TZDateTime inZone(DateTime instant, String? timezone) =>
    tz.TZDateTime.from(instant.toUtc(), _location(timezone));

/// "Mon 16 Nov, 10:00–11:00" in the organization's timezone. Spans over
/// midnight show both dates.
String formatWindow(DateTime start, DateTime end, String? timezone) {
  final s = inZone(start, timezone);
  final e = inZone(end, timezone);
  final day = DateFormat('EEE d MMM');
  final time = DateFormat('HH:mm');
  final sameDay = s.year == e.year && s.month == e.month && s.day == e.day;
  if (sameDay) {
    return '${day.format(s)}, ${time.format(s)}–${time.format(e)}';
  }
  return '${day.format(s)} ${time.format(s)} – ${day.format(e)} ${time.format(e)}';
}

/// "16 Nov 2026, 10:00" in the organization's timezone.
String formatDateTime(DateTime instant, String? timezone) =>
    DateFormat('d MMM y, HH:mm').format(inZone(instant, timezone));

/// Formats integer minor units (tyiyn) as "1 200.00 KGS".
String formatMoney(int minor, [String currency = 'KGS']) {
  final negative = minor < 0;
  final abs = minor.abs();
  final whole = (abs ~/ 100).toString();
  final cents = (abs % 100).toString().padLeft(2, '0');
  final grouped = StringBuffer();
  for (var i = 0; i < whole.length; i++) {
    if (i > 0 && (whole.length - i) % 3 == 0) grouped.write(' ');
    grouped.write(whole[i]);
  }
  return '${negative ? '-' : ''}$grouped.$cents $currency';
}

/// "HELLO_WORLD" -> "Hello world".
String humanizeEnum(String value) {
  final s = value.replaceAll('_', ' ').toLowerCase();
  return s.isEmpty ? s : s[0].toUpperCase() + s.substring(1);
}

/// 90 -> "1 h 30 min".
String formatMinutes(int minutes) {
  final h = minutes ~/ 60;
  final m = minutes % 60;
  if (h == 0) return '$m min';
  if (m == 0) return '$h h';
  return '$h h $m min';
}
