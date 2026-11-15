import type { components } from "./schema";

/** Convenience aliases over the generated OpenAPI schema (regenerate with `bun run gen:api`). */
export type Schemas = components["schemas"];
export type RequestDetail = Schemas["RequestDetail"];
export type RequestListItem = Schemas["RequestListItem"];
export type RequestStatus = Schemas["RequestStatus"];
export type Priority = Schemas["Priority"];
export type NoteOut = Schemas["NoteOut"];
export type NoteVisibility = Schemas["NoteVisibility"];
export type TimelineItem = Schemas["TimelineItem"];
export type FileOut = Schemas["FileOut"];
export type NotificationOut = Schemas["NotificationOut"];
export type MembershipOut = Schemas["MembershipOut"];
export type UserBrief = Schemas["UserBrief"];
export type LoginResponse = Schemas["LoginResponse"];
export type Role = Schemas["MembershipRole"];
export type SlaState = "ON_TRACK" | "AT_RISK" | "OVERDUE" | "PAUSED";

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export const REQUEST_STATUSES: RequestStatus[] = [
  "SUBMITTED",
  "TRIAGED",
  "SCHEDULED",
  "ACCEPTED",
  "IN_PROGRESS",
  "BLOCKED",
  "COMPLETED",
  "CLOSED",
  "REOPENED",
  "CANCELED",
];
