import 'package:fixflow_tech/app.dart';
import 'package:fixflow_tech/core/auth/models.dart';
import 'package:fixflow_tech/core/auth/session.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/fixtures.dart';

SessionState signedIn(List<Membership> ms, [String? org]) => SessionState(
  status: SessionStatus.signedIn,
  token: 't',
  user: const UserProfile(id: 'u', email: 'e@x.y', fullName: 'E'),
  memberships: ms,
  selectedOrgId: org,
);

void main() {
  group('resolveOrgRoute', () {
    test('no technician membership', () {
      final s = signedIn([
        membership('o1', 'DISPATCHER'),
        membership('o2', 'ADMIN'),
      ]);
      expect(s.technicianMemberships, isEmpty);
      expect(s.route, OrgRoute.noTechnicianAccess);
    });
    test('one technician membership goes straight to inbox', () {
      final s = signedIn([
        membership('o1', 'TECHNICIAN'),
        membership('o2', 'ADMIN'),
      ]);
      expect(s.route, OrgRoute.inbox);
      expect(autoSelectOrgId(s.technicianMemberships, null), 'o1');
    });
    test('several memberships require selection', () {
      final ms = [
        membership('o1', 'TECHNICIAN'),
        membership('o2', 'TECHNICIAN'),
      ];
      expect(signedIn(ms).route, OrgRoute.selectOrg);
      expect(signedIn(ms, 'o2').route, OrgRoute.inbox);
      expect(signedIn(ms, 'unknown').route, OrgRoute.selectOrg);
      expect(signedIn(ms, 'o2').selectedOrg?.id, 'o2');
    });
    test('previous selection is kept only when still valid', () {
      final ms = [
        membership('o1', 'TECHNICIAN'),
        membership('o2', 'TECHNICIAN'),
      ];
      expect(autoSelectOrgId(ms, 'o2'), 'o2');
      expect(autoSelectOrgId(ms, 'gone'), isNull);
    });
  });

  group('router redirects', () {
    test('bootstrapping -> splash', () {
      expect(
        redirectFor(const SessionState.bootstrapping(), '/inbox'),
        '/splash',
      );
    });
    test('signed out / expired -> sign-in', () {
      expect(redirectFor(const SessionState.signedOut(), '/inbox'), '/sign-in');
      expect(
        redirectFor(
          const SessionState(status: SessionStatus.expired),
          '/jobs/1',
        ),
        '/sign-in',
      );
      expect(redirectFor(const SessionState.signedOut(), '/sign-in'), isNull);
    });
    test('signed-in routing by membership', () {
      final one = signedIn([membership('o1', 'TECHNICIAN')]);
      expect(redirectFor(one, '/sign-in'), '/inbox');
      expect(redirectFor(one, '/jobs/1'), isNull);
      expect(redirectFor(one, '/select-org'), '/inbox');
      final none = signedIn([membership('o1', 'ADMIN')]);
      expect(redirectFor(none, '/inbox'), '/no-access');
      final many = signedIn([
        membership('o1', 'TECHNICIAN'),
        membership('o2', 'TECHNICIAN'),
      ]);
      expect(redirectFor(many, '/inbox'), '/select-org');
      expect(
        redirectFor(many.copyWith(selectedOrgId: 'o1'), '/select-org'),
        isNull,
      );
    });
  });
}
