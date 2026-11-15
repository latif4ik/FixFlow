import 'package:fixflow_tech/core/auth/models.dart';
import 'package:fixflow_tech/features/jobs/job_models.dart';

Map<String, dynamic> membershipJson(
  String orgId,
  String role, {
  String tz = 'Asia/Bishkek',
}) => {
  'membership_id': 'm-$orgId-$role',
  'organization': {'id': orgId, 'name': 'Org $orgId', 'timezone': tz},
  'role': role,
};

Membership membership(
  String orgId,
  String role, {
  String tz = 'Asia/Bishkek',
}) => Membership.fromJson(membershipJson(orgId, role, tz: tz));

Map<String, dynamic> loginJson({List<Map<String, dynamic>>? memberships}) => {
  'token': 'tok-123',
  'expires_at': '2099-01-01T00:00:00Z',
  'user': {'id': 'u1', 'email': 'tech@x.demo', 'full_name': 'Tech One'},
  'memberships': memberships ?? [membershipJson('o1', 'TECHNICIAN')],
};

Map<String, dynamic> assignmentJson({
  String id = 'r1',
  String display = 'REQ-7',
  String status = 'SCHEDULED',
}) => {
  'assignment_id': 'a-$id',
  'request': {
    'id': id,
    'display_id': display,
    'title': 'Replace corridor lights',
    'description': 'desc',
    'status': status,
    'priority': 'HIGH',
    'category': {'id': 'c', 'name': 'Electrical'},
    'property': {
      'name': 'Northwind HQ Tower',
      'address': '12 Chuy Ave, Bishkek',
      'contact_instructions': 'Check in at the front desk.',
    },
    'asset': null,
    'requester_name': 'Req One',
  },
  // 04:00Z == 10:00 in Asia/Bishkek (UTC+6)
  'appointment': {
    'start_at': '2026-11-16T04:00:00Z',
    'end_at': '2026-11-16T05:00:00Z',
  },
  'assignment_status': 'ACTIVE',
  'allowed_actions': ['accept', 'decline', 'add_note'],
  'estimate_status': null,
  'start_blocked_reason': null,
};

AssignmentItem assignment({String id = 'r1', String display = 'REQ-7'}) =>
    AssignmentItem.fromJson(assignmentJson(id: id, display: display));

Map<String, dynamic> jobJson() => {
  'id': 'r1',
  'display_id': 'REQ-10',
  'title': 'Repair the stuck service door',
  'status': 'BLOCKED',
  'priority': 'HIGH',
  'category': {'id': 'c', 'name': 'General maintenance'},
  'property': {
    'id': 'p',
    'name': 'Riverside Mall',
    'address': '88 Sovetskaya St, Bishkek',
  },
  'asset': {'id': 'as', 'code': 'AC-12', 'name': 'Rooftop unit'},
  'requester': {'membership_id': 'x', 'name': 'Requester One'},
  'sla_state': 'AT_RISK',
  'appointment': {
    'start_at': '2026-11-16T08:00:00Z',
    'end_at': '2026-11-16T09:00:00Z',
  },
  'description': 'The door is stuck.',
  'notes': [
    {
      'id': 'n1',
      'kind': 'BLOCKER',
      'visibility': 'PUBLIC',
      'body': 'Waiting for a replacement hinge.',
      'author': {'membership_id': 'm', 'name': 'Technician One'},
      'created_at': '2026-11-15T08:09:49Z',
      'attachments': [],
    },
  ],
  'files': [],
  'timeline': [
    {
      'id': 't1',
      'type': 'STATUS_CHANGED',
      'label': 'Status changed',
      'actor': {'membership_id': 'm', 'name': 'Technician One'},
      'from_status': 'IN_PROGRESS',
      'to_status': 'BLOCKED',
      'created_at': '2026-11-15T08:09:49Z',
    },
  ],
  'allowed_actions': ['resume', 'add_note'],
  'estimate': {
    'id': 'e',
    'version': 2,
    'status': 'APPROVED',
    'total_minor': 120000,
    'currency': 'KGS',
    'labor_minutes': 60,
    'labor_cost_minor': 60000,
    'materials_total_minor': 60000,
    'lines': [],
  },
  'sla': {
    'state': 'AT_RISK',
    'paused': false,
    'stopped': false,
    'due_at': '2026-11-17T08:00:00Z',
    'remaining_minutes': 30,
    'overdue_by_minutes': 0,
  },
  'materials': [],
};
