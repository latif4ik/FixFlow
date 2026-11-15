import type { RequestDetail, Role } from "@/lib/api/types";
import type { RequestActionContext } from "@/features/request-actions/types";
import { ORG_A } from "@/test/render";

/** Minimal RequestDetail for panel tests. Preferred window 11:00-12:30 on 16 Nov 2026 (Asia/Bishkek). */
export function makeDetail(over: Record<string, unknown> = {}): RequestDetail {
  return {
    id: "r1",
    number: 14,
    display_id: "REQ-14",
    title: "Chiller noise in the server room",
    status: "TRIAGED",
    priority: "HIGH",
    category: { id: "cat-hvac", name: "HVAC" },
    property: { id: "p1", name: "Northwind HQ Tower", address: "12 Chuy Ave" },
    asset: null,
    requester: { membership_id: "m-req", name: "Req One" },
    created_at: "2026-11-14T23:57:56Z",
    updated_at: "2026-11-14T23:57:56Z",
    sla_state: "ON_TRACK",
    sla_due_at: "2026-11-16T11:00:00Z",
    description: "Noise",
    preferred_window_start: "2026-11-16T05:00:00Z",
    preferred_window_end: "2026-11-16T06:30:00Z",
    duplicate_of: null,
    notes: [],
    files: [],
    timeline: [],
    allowed_actions: ["assign", "suggest_assignment", "cancel", "add_note", "edit_priority_category", "link_duplicate"],
    assignment: null,
    appointment: null,
    estimate: null,
    materials: [],
    feedback: null,
    ...over,
  } as unknown as RequestDetail;
}

export function makeCtx(detailOver: Record<string, unknown> = {}, role: Role = "DISPATCHER"): RequestActionContext {
  const detail = makeDetail(detailOver);
  return { requestId: detail.id, detail, orgId: ORG_A.id, role, timezone: ORG_A.timezone, allowed: new Set(detail.allowed_actions) };
}

export const CATEGORY_HVAC = {
  id: "cat-hvac",
  name: "HVAC",
  description: null,
  default_duration_minutes: 90,
  is_enabled: true,
  required_skills: [{ id: "sk1", name: "HVAC" }],
  created_at: "2026-11-14T00:00:00Z",
  updated_at: "2026-11-14T00:00:00Z",
};
