/**
 * Query key factory. INVARIANT: every key starts with ['org', orgId, ...] so a prefix invalidation / clear is
 * always tenant-scoped and a cache entry can never be served for another org (WEB-07).
 * Add keys for your feature by calling `qk.custom(orgId, 'my-feature', ...)` or extend your own factory built on `orgKey`.
 */
export type OrgKey = readonly ["org", string, ...unknown[]];
export type Params = Record<string, unknown> | undefined;

export const orgKey = (orgId: string, ...parts: unknown[]): OrgKey => ["org", orgId, ...parts];

const group = (name: string) => ({
  all: (orgId: string) => orgKey(orgId, name),
  list: (orgId: string, params?: Params) => orgKey(orgId, name, "list", params ?? {}),
  detail: (orgId: string, id: string) => orgKey(orgId, name, "detail", id),
});

export const qk = {
  /** Everything for an org. */
  all: (orgId: string) => orgKey(orgId),
  custom: orgKey,
  me: { membership: (orgId: string) => orgKey(orgId, "me", "membership") },
  requests: {
    ...group("requests"),
    notes: (orgId: string, id: string) => orgKey(orgId, "requests", "detail", id, "notes"),
    timeline: (orgId: string, id: string) => orgKey(orgId, "requests", "detail", id, "timeline"),
    suggestions: (orgId: string, id: string, params?: Params) => orgKey(orgId, "requests", "detail", id, "suggestions", params ?? {}),
    candidates: (orgId: string, id: string, params?: Params) => orgKey(orgId, "requests", "detail", id, "candidates", params ?? {}),
    estimates: (orgId: string, id: string) => orgKey(orgId, "requests", "detail", id, "estimates"),
    materials: (orgId: string, id: string) => orgKey(orgId, "requests", "detail", id, "materials"),
  },
  myAssignments: { ...group("my-assignments") },
  notifications: {
    ...group("notifications"),
    unreadCount: (orgId: string) => orgKey(orgId, "notifications", "unread-count"),
  },
  dashboard: {
    all: (orgId: string) => orgKey(orgId, "dashboard"),
    overdue: (orgId: string, params?: Params) => orgKey(orgId, "dashboard", "overdue", params ?? {}),
    overdueCount: (orgId: string) => orgKey(orgId, "dashboard", "overdue-count"),
  },
  reports: {
    all: (orgId: string) => orgKey(orgId, "reports"),
    summary: (orgId: string, params?: Params) => orgKey(orgId, "reports", "summary", params ?? {}),
    daily: (orgId: string, params?: Params) => orgKey(orgId, "reports", "daily", params ?? {}),
    distribution: (orgId: string, params?: Params) => orgKey(orgId, "reports", "distribution", params ?? {}),
  },
  schedule: {
    all: (orgId: string) => orgKey(orgId, "schedule"),
    range: (orgId: string, params?: Params) => orgKey(orgId, "schedule", params ?? {}),
  },
  estimates: group("estimates"),
  properties: { ...group("properties"), access: (orgId: string, id: string) => orgKey(orgId, "properties", "detail", id, "access") },
  assets: { ...group("assets"), history: (orgId: string, id: string, params?: Params) => orgKey(orgId, "assets", "detail", id, "history", params ?? {}) },
  technicians: group("technicians"),
  categories: group("categories"),
  skills: group("skills"),
  members: group("members"),
  inventory: { ...group("inventory"), lowStock: (orgId: string) => orgKey(orgId, "inventory", "low-stock"), movements: (orgId: string, id: string) => orgKey(orgId, "inventory", "detail", id, "movements") },
  maintenance: group("maintenance-plans"),
  org: {
    settings: (orgId: string) => orgKey(orgId, "org", "settings"),
    businessHours: (orgId: string) => orgKey(orgId, "org", "business-hours"),
    holidays: (orgId: string) => orgKey(orgId, "org", "holidays"),
  },
  audit: group("audit"),
} as const;

/** Prefixes invalidated whenever the server says a request changed (see lib/live). */
export function requestChangedPrefixes(orgId: string, requestId?: string): OrgKey[] {
  const keys: OrgKey[] = [
    qk.requests.all(orgId),
    qk.dashboard.all(orgId),
    qk.reports.all(orgId),
    qk.schedule.all(orgId),
    qk.estimates.all(orgId),
    qk.assets.all(orgId),
    qk.myAssignments.all(orgId),
  ];
  if (requestId) keys.push(qk.requests.detail(orgId, requestId));
  return keys;
}
