import 'models.dart';

enum SessionStatus {
  /// Reading persisted session at startup.
  bootstrapping,
  signedOut,

  /// Server rejected the token (401). User must sign in again; local queued
  /// work (M2) is kept.
  expired,
  signedIn,
}

/// Where a signed-in user should land (pure function, unit-tested).
enum OrgRoute { noTechnicianAccess, selectOrg, inbox }

class SessionState {
  const SessionState({
    required this.status,
    this.token,
    this.user,
    this.memberships = const [],
    this.selectedOrgId,
    this.lastEmail,
  });

  const SessionState.bootstrapping()
    : this(status: SessionStatus.bootstrapping);
  const SessionState.signedOut({String? lastEmail})
    : this(status: SessionStatus.signedOut, lastEmail: lastEmail);

  final SessionStatus status;

  /// In-memory copy of the bearer token. Never persisted outside secure
  /// storage and never logged ([toString] is overridden).
  final String? token;
  final UserProfile? user;
  final List<Membership> memberships;
  final String? selectedOrgId;

  /// Prefill for the sign-in form after sign-out / expiry.
  final String? lastEmail;

  bool get isSignedIn => status == SessionStatus.signedIn;

  /// Only TECHNICIAN memberships are usable in this app.
  List<Membership> get technicianMemberships =>
      memberships.where((m) => m.isTechnician).toList(growable: false);

  Membership? get selectedMembership {
    for (final m in technicianMemberships) {
      if (m.organization.id == selectedOrgId) return m;
    }
    return null;
  }

  Organization? get selectedOrg => selectedMembership?.organization;

  OrgRoute get route => resolveOrgRoute(technicianMemberships, selectedOrgId);

  SessionState copyWith({String? selectedOrgId, bool clearOrg = false}) =>
      SessionState(
        status: status,
        token: token,
        user: user,
        memberships: memberships,
        selectedOrgId: clearOrg ? null : (selectedOrgId ?? this.selectedOrgId),
        lastEmail: lastEmail,
      );

  @override
  String toString() => 'SessionState($status, org: $selectedOrgId)';
}

/// No technician membership -> dead end with sign-out; one -> straight to the
/// inbox; several -> org selector until one is chosen.
OrgRoute resolveOrgRoute(List<Membership> technician, String? selectedOrgId) {
  if (technician.isEmpty) return OrgRoute.noTechnicianAccess;
  if (technician.length == 1) return OrgRoute.inbox;
  final valid = technician.any((m) => m.organization.id == selectedOrgId);
  return valid ? OrgRoute.inbox : OrgRoute.selectOrg;
}

/// With exactly one technician membership it is selected automatically.
String? autoSelectOrgId(List<Membership> technician, String? previous) {
  if (technician.length == 1) return technician.first.organization.id;
  if (technician.any((m) => m.organization.id == previous)) return previous;
  return null;
}
