import 'package:fixflow_tech/core/config/app_config.dart';
import 'package:fixflow_tech/core/util/formatters.dart';
import 'package:fixflow_tech/features/auth/validators.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  setUpAll(initTimezones);

  group('formatMoney', () {
    test('formats tyiyn with grouping', () {
      expect(formatMoney(120000), '1 200.00 KGS');
      expect(formatMoney(0), '0.00 KGS');
      expect(formatMoney(5), '0.05 KGS');
      expect(formatMoney(123456789, 'KGS'), '1 234 567.89 KGS');
      expect(formatMoney(-250050), '-2 500.50 KGS');
      expect(formatMoney(100000000), '1 000 000.00 KGS');
    });
  });

  group('formatWindow', () {
    test('renders in the org timezone (Asia/Bishkek = UTC+6)', () {
      final s = DateTime.utc(2026, 11, 16, 4);
      final e = DateTime.utc(2026, 11, 16, 5);
      expect(formatWindow(s, e, 'Asia/Bishkek'), 'Mon 16 Nov, 10:00–11:00');
      expect(formatWindow(s, e, 'UTC'), 'Mon 16 Nov, 04:00–05:00');
    });
    test('handles a zone with DST and crossing midnight', () {
      final s = DateTime.utc(2026, 7, 2, 3); // New York EDT = UTC-4
      final e = DateTime.utc(2026, 7, 2, 5);
      expect(
        formatWindow(s, e, 'America/New_York'),
        'Wed 1 Jul 23:00 – Thu 2 Jul 01:00',
      );
    });
    test('unknown zone falls back to UTC', () {
      final s = DateTime.utc(2026, 11, 16, 4);
      expect(formatDateTime(s, 'Not/AZone'), '16 Nov 2026, 04:00');
    });
  });

  group('server url validation', () {
    test('accepts http(s) urls', () {
      expect(validateServerUrl('http://192.168.1.20:8000'), isNull);
      expect(validateServerUrl(' https://api.example.com/ '), isNull);
    });
    test('rejects bad input', () {
      expect(validateServerUrl(''), isNotNull);
      expect(validateServerUrl('192.168.1.20:8000'), isNotNull);
      expect(validateServerUrl('ftp://x.com'), isNotNull);
      expect(validateServerUrl('http://'), isNotNull);
      expect(validateServerUrl('http://u:p@host'), isNotNull);
    });
    test('normalize strips trailing slashes', () {
      expect(normalizeServerUrl(' http://a:8000// '), 'http://a:8000');
    });
  });

  group('credentials validators', () {
    test('email', () {
      expect(validateEmail(''), isNotNull);
      expect(validateEmail('nope'), isNotNull);
      expect(validateEmail('a@b'), isNotNull);
      expect(validateEmail('technician1@northwind.demo'), isNull);
    });
    test('password', () {
      expect(validatePassword(''), isNotNull);
      expect(validatePassword('x'), isNull);
    });
  });
}
