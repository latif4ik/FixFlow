class Organization {
  const Organization({
    required this.id,
    required this.name,
    required this.timezone,
  });

  factory Organization.fromJson(Map<String, dynamic> j) => Organization(
    id: j['id'] as String,
    name: j['name'] as String,
    timezone: (j['timezone'] as String?) ?? 'UTC',
  );

  final String id;
  final String name;

  /// IANA zone, e.g. Asia/Bishkek. All times are rendered in it.
  final String timezone;

  Map<String, dynamic> toJson() => {
    'id': id,
    'name': name,
    'timezone': timezone,
  };
}

class Membership {
  const Membership({
    required this.membershipId,
    required this.organization,
    required this.role,
  });

  factory Membership.fromJson(Map<String, dynamic> j) => Membership(
    membershipId: j['membership_id'] as String,
    organization: Organization.fromJson(
      (j['organization'] as Map).cast<String, dynamic>(),
    ),
    role: j['role'] as String,
  );

  final String membershipId;
  final Organization organization;
  final String role;

  bool get isTechnician => role == 'TECHNICIAN';

  Map<String, dynamic> toJson() => {
    'membership_id': membershipId,
    'organization': organization.toJson(),
    'role': role,
  };
}

class UserProfile {
  const UserProfile({
    required this.id,
    required this.email,
    required this.fullName,
  });

  factory UserProfile.fromJson(Map<String, dynamic> j) => UserProfile(
    id: j['id'] as String,
    email: j['email'] as String,
    fullName: (j['full_name'] as String?) ?? (j['email'] as String),
  );

  final String id;
  final String email;
  final String fullName;
}

/// Result of POST /auth/login.
class LoginResult {
  const LoginResult({
    required this.token,
    required this.expiresAt,
    required this.user,
    required this.memberships,
  });

  factory LoginResult.fromJson(Map<String, dynamic> j) => LoginResult(
    token: j['token'] as String,
    expiresAt: DateTime.tryParse((j['expires_at'] as String?) ?? ''),
    user: UserProfile.fromJson((j['user'] as Map).cast<String, dynamic>()),
    memberships: [
      for (final m in (j['memberships'] as List? ?? const []))
        Membership.fromJson((m as Map).cast<String, dynamic>()),
    ],
  );

  final String token;
  final DateTime? expiresAt;
  final UserProfile user;
  final List<Membership> memberships;
}
