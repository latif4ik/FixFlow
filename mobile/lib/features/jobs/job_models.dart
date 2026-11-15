/// Read models for the technician's jobs. Parsed defensively: unknown/missing
/// optional fields never crash the UI.
Map<String, dynamic>? _map(Object? o) =>
    o is Map ? o.cast<String, dynamic>() : null;

DateTime? _date(Object? o) => o is String ? DateTime.tryParse(o) : null;

class PropertyInfo {
  const PropertyInfo({
    this.id,
    required this.name,
    required this.address,
    this.contactInstructions,
  });

  factory PropertyInfo.fromJson(Map<String, dynamic> j) => PropertyInfo(
    id: j['id'] as String?,
    name: (j['name'] ?? '') as String,
    address: (j['address'] ?? '') as String,
    contactInstructions: j['contact_instructions'] as String?,
  );

  final String? id;
  final String name;
  final String address;
  final String? contactInstructions;
}

class AssetInfo {
  const AssetInfo({
    this.id,
    required this.code,
    required this.name,
    this.serial,
  });

  factory AssetInfo.fromJson(Map<String, dynamic> j) => AssetInfo(
    id: j['id'] as String?,
    code: (j['code'] ?? '') as String,
    name: (j['name'] ?? '') as String,
    serial: (j['serial_number'] ?? j['serial']) as String?,
  );

  final String? id;
  final String code;
  final String name;
  final String? serial;
}

class Appointment {
  const Appointment({required this.start, required this.end});
  static Appointment? fromJson(Map<String, dynamic>? j) {
    if (j == null) return null;
    final s = _date(j['start_at']);
    final e = _date(j['end_at']);
    return s == null || e == null ? null : Appointment(start: s, end: e);
  }

  final DateTime start;
  final DateTime end;
}

/// Item of GET /me/assignments.
class AssignmentItem {
  const AssignmentItem({
    required this.assignmentId,
    required this.requestId,
    required this.displayId,
    required this.title,
    required this.description,
    required this.status,
    required this.priority,
    required this.categoryName,
    required this.property,
    this.asset,
    this.appointment,
    required this.assignmentStatus,
    required this.allowedActions,
    this.estimateStatus,
    this.startBlockedReason,
    this.raw,
  });

  factory AssignmentItem.fromJson(Map<String, dynamic> j) {
    final r = _map(j['request']) ?? const {};
    return AssignmentItem(
      assignmentId: j['assignment_id'] as String,
      requestId: r['id'] as String,
      displayId: (r['display_id'] ?? '') as String,
      title: (r['title'] ?? '') as String,
      description: (r['description'] ?? '') as String,
      status: (r['status'] ?? '') as String,
      priority: (r['priority'] ?? 'NORMAL') as String,
      categoryName: (_map(r['category'])?['name'] ?? '') as String,
      property: PropertyInfo.fromJson(_map(r['property']) ?? const {}),
      asset: _map(r['asset']) == null
          ? null
          : AssetInfo.fromJson(_map(r['asset'])!),
      appointment: Appointment.fromJson(_map(j['appointment'])),
      assignmentStatus: (j['assignment_status'] ?? '') as String,
      allowedActions: [
        for (final a in (j['allowed_actions'] as List? ?? const []))
          a as String,
      ],
      estimateStatus: j['estimate_status'] as String?,
      startBlockedReason: j['start_blocked_reason'] as String?,
      raw: j,
    );
  }

  /// Original server JSON (kept so the offline cache can store it verbatim).
  final Map<String, dynamic>? raw;
  final String assignmentId;
  final String requestId;
  final String displayId;
  final String title;
  final String description;
  final String status;
  final String priority;
  final String categoryName;
  final PropertyInfo property;
  final AssetInfo? asset;
  final Appointment? appointment;
  final String assignmentStatus;
  final List<String> allowedActions;
  final String? estimateStatus;
  final String? startBlockedReason;
}

class AssignmentPage {
  const AssignmentPage({
    required this.items,
    required this.total,
    required this.page,
    required this.pageSize,
    this.stale = false,
    this.syncedAt,
  });

  factory AssignmentPage.fromJson(Map<String, dynamic> j) => AssignmentPage(
    items: [
      for (final i in (j['items'] as List? ?? const []))
        AssignmentItem.fromJson((i as Map).cast<String, dynamic>()),
    ],
    total: (j['total'] as num?)?.toInt() ?? 0,
    page: (j['page'] as num?)?.toInt() ?? 1,
    pageSize: (j['page_size'] as num?)?.toInt() ?? 20,
  );

  final List<AssignmentItem> items;
  final int total;
  final int page;
  final int pageSize;

  /// True when served from the offline cache; [syncedAt] is when it was last
  /// synchronized with the server.
  final bool stale;
  final DateTime? syncedAt;
}

enum AssignmentScope {
  upcoming,
  active,
  history;

  String get label => switch (this) {
    upcoming => 'Upcoming',
    active => 'Active',
    history => 'History',
  };
}

class EstimateLine {
  const EstimateLine({
    required this.description,
    required this.quantity,
    required this.unitPriceMinor,
    required this.lineTotalMinor,
  });
  final String description;
  final String quantity;
  final int unitPriceMinor;
  final int lineTotalMinor;
}

class EstimateInfo {
  const EstimateInfo({
    required this.status,
    required this.version,
    required this.totalMinor,
    required this.currency,
    required this.laborMinutes,
    required this.laborCostMinor,
    required this.materialsTotalMinor,
    required this.lines,
  });

  static EstimateInfo? fromJson(Map<String, dynamic>? j) {
    if (j == null) return null;
    return EstimateInfo(
      status: (j['status'] ?? '') as String,
      version: (j['version'] as num?)?.toInt() ?? 1,
      totalMinor: (j['total_minor'] as num?)?.toInt() ?? 0,
      currency: (j['currency'] ?? 'KGS') as String,
      laborMinutes: (j['labor_minutes'] as num?)?.toInt() ?? 0,
      laborCostMinor: (j['labor_cost_minor'] as num?)?.toInt() ?? 0,
      materialsTotalMinor: (j['materials_total_minor'] as num?)?.toInt() ?? 0,
      lines: [
        for (final l in (j['lines'] as List? ?? const []))
          EstimateLine(
            description: (l['description'] ?? '') as String,
            quantity: (l['quantity'] ?? '').toString(),
            unitPriceMinor: (l['unit_price_minor'] as num?)?.toInt() ?? 0,
            lineTotalMinor: (l['line_total_minor'] as num?)?.toInt() ?? 0,
          ),
      ],
    );
  }

  final String status;
  final int version;
  final int totalMinor;
  final String currency;
  final int laborMinutes;
  final int laborCostMinor;
  final int materialsTotalMinor;
  final List<EstimateLine> lines;
}

class SlaInfo {
  const SlaInfo({
    required this.state,
    this.dueAt,
    required this.paused,
    required this.stopped,
    required this.remainingMinutes,
    required this.overdueByMinutes,
  });

  static SlaInfo? fromJson(Map<String, dynamic>? j) {
    if (j == null) return null;
    return SlaInfo(
      state: (j['state'] ?? '') as String,
      dueAt: _date(j['due_at']),
      paused: j['paused'] == true,
      stopped: j['stopped'] == true,
      remainingMinutes: (j['remaining_minutes'] as num?)?.toInt() ?? 0,
      overdueByMinutes: (j['overdue_by_minutes'] as num?)?.toInt() ?? 0,
    );
  }

  final String state;
  final DateTime? dueAt;
  final bool paused;
  final bool stopped;
  final int remainingMinutes;
  final int overdueByMinutes;
}

class JobNote {
  const JobNote({
    required this.id,
    required this.kind,
    required this.visibility,
    required this.body,
    this.authorName,
    required this.createdAt,
    required this.attachmentCount,
  });
  final String id;
  final String kind;
  final String visibility;
  final String body;
  final String? authorName;
  final DateTime createdAt;
  final int attachmentCount;
}

class TimelineEntry {
  const TimelineEntry({
    required this.id,
    required this.label,
    this.actorName,
    this.fromStatus,
    this.toStatus,
    required this.createdAt,
  });
  final String id;
  final String label;
  final String? actorName;
  final String? fromStatus;
  final String? toStatus;
  final DateTime createdAt;
}

class MaterialUsage {
  const MaterialUsage({
    required this.name,
    required this.quantity,
    required this.totalCostMinor,
    required this.currency,
  });
  final String name;
  final String quantity;
  final int totalCostMinor;
  final String currency;
}

/// GET /requests/{id}.
class JobDetail {
  const JobDetail({
    required this.id,
    required this.displayId,
    required this.title,
    required this.description,
    required this.status,
    required this.priority,
    required this.categoryName,
    required this.property,
    this.asset,
    this.requesterName,
    this.appointment,
    this.estimate,
    this.sla,
    required this.allowedActions,
    required this.notes,
    required this.timeline,
    required this.attachmentCount,
    required this.materials,
    this.raw,
    this.stale = false,
    this.syncedAt,
  });

  factory JobDetail.fromJson(Map<String, dynamic> j) {
    final notes = <JobNote>[
      for (final n in (j['notes'] as List? ?? const []))
        JobNote(
          id: n['id'] as String,
          kind: (n['kind'] ?? 'GENERAL') as String,
          visibility: (n['visibility'] ?? 'PUBLIC') as String,
          body: (n['body'] ?? '') as String,
          authorName: _map(n['author'])?['name'] as String?,
          createdAt: _date(n['created_at']) ?? DateTime.now(),
          attachmentCount: (n['attachments'] as List?)?.length ?? 0,
        ),
    ];
    return JobDetail(
      id: j['id'] as String,
      displayId: (j['display_id'] ?? '') as String,
      title: (j['title'] ?? '') as String,
      description: (j['description'] ?? '') as String,
      status: (j['status'] ?? '') as String,
      priority: (j['priority'] ?? 'NORMAL') as String,
      categoryName: (_map(j['category'])?['name'] ?? '') as String,
      property: PropertyInfo.fromJson(_map(j['property']) ?? const {}),
      asset: _map(j['asset']) == null
          ? null
          : AssetInfo.fromJson(_map(j['asset'])!),
      requesterName: _map(j['requester'])?['name'] as String?,
      appointment: Appointment.fromJson(_map(j['appointment'])),
      estimate: EstimateInfo.fromJson(_map(j['estimate'])),
      sla: SlaInfo.fromJson(_map(j['sla'])),
      allowedActions: [
        for (final a in (j['allowed_actions'] as List? ?? const []))
          a as String,
      ],
      notes: notes,
      timeline: [
        for (final t in (j['timeline'] as List? ?? const []))
          TimelineEntry(
            id: t['id'] as String,
            label: (t['label'] ?? t['type'] ?? '') as String,
            actorName: _map(t['actor'])?['name'] as String?,
            fromStatus: t['from_status'] as String?,
            toStatus: t['to_status'] as String?,
            createdAt: _date(t['created_at']) ?? DateTime.now(),
          ),
      ],
      attachmentCount: (j['files'] as List?)?.length ?? 0,
      materials: [
        for (final m in (j['materials'] as List? ?? const []))
          MaterialUsage(
            name: (_map(m['item'])?['name'] ?? 'Material') as String,
            quantity: (m['quantity'] ?? '').toString(),
            totalCostMinor: (m['total_cost_minor'] as num?)?.toInt() ?? 0,
            currency: (m['currency'] ?? 'KGS') as String,
          ),
      ],
      raw: j,
    );
  }

  /// Same job flagged as served from the offline cache.
  JobDetail asStale(DateTime syncedAt) => JobDetail(
    id: id,
    displayId: displayId,
    title: title,
    description: description,
    status: status,
    priority: priority,
    categoryName: categoryName,
    property: property,
    asset: asset,
    requesterName: requesterName,
    appointment: appointment,
    estimate: estimate,
    sla: sla,
    allowedActions: allowedActions,
    notes: notes,
    timeline: timeline,
    attachmentCount: attachmentCount,
    materials: materials,
    raw: raw,
    stale: true,
    syncedAt: syncedAt,
  );

  final Map<String, dynamic>? raw;
  final bool stale;
  final DateTime? syncedAt;
  final String id;
  final String displayId;
  final String title;
  final String description;
  final String status;
  final String priority;
  final String categoryName;
  final PropertyInfo property;
  final AssetInfo? asset;
  final String? requesterName;
  final Appointment? appointment;
  final EstimateInfo? estimate;
  final SlaInfo? sla;
  final List<String> allowedActions;
  final List<JobNote> notes;
  final List<TimelineEntry> timeline;
  final int attachmentCount;
  final List<MaterialUsage> materials;
}
