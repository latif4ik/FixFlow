/**
 * Human-readable labels for API enums. Never render a raw enum value (`AWAITING_APPROVAL`) in the UI.
 */
import type { RequestStatus } from "@/lib/api/types";

/** `AWAITING_APPROVAL` -> `Awaiting approval`. Safe for any SCREAMING_SNAKE enum. */
export function humanize(value: string): string {
  const s = value.replaceAll("_", " ").trim().toLowerCase();
  return s.charAt(0).toUpperCase() + s.slice(1);
}

export const ESTIMATE_STATUS_LABEL: Record<string, string> = {
  DRAFT: "Draft",
  AWAITING_APPROVAL: "Awaiting approval",
  APPROVED: "Approved",
  REJECTED: "Rejected",
  WITHDRAWN: "Withdrawn",
  SUPERSEDED: "Superseded",
};

export function estimateStatusLabel(status: string): string {
  return ESTIMATE_STATUS_LABEL[status] ?? humanize(status);
}

/** Sentence-case request status for running text ("in progress"). */
export function requestStatusText(status: RequestStatus | string): string {
  return humanize(status).toLowerCase();
}

export type RowAction = "assign" | "triage" | "open";

/**
 * Primary action for a request row in overdue lists: Smart assign only when a technician can actually be
 * assigned (TRIAGED); SUBMITTED / REOPENED still need triage; everything else just opens the request.
 */
export function rowActionFor(status: RequestStatus | string): RowAction {
  if (status === "TRIAGED") return "assign";
  if (status === "SUBMITTED" || status === "REOPENED") return "triage";
  return "open";
}

export function rowActionHref(id: string, status: RequestStatus | string): string {
  const a = rowActionFor(status);
  return a === "assign" ? `/requests/${id}#assign` : a === "triage" ? `/requests/${id}#triage` : `/requests/${id}`;
}
