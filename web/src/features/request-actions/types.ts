import type { ComponentType } from "react";
import type { RequestDetail, Role } from "@/lib/api/types";

/** Where the detail page renders the component. */
export type ActionPlacement = "header" | "sidebar" | "main";

export interface RequestActionContext {
  requestId: string;
  /** Fresh detail from GET /requests/{id} (refetched automatically after invalidation / live events). */
  detail: RequestDetail;
  orgId: string;
  role: Role;
  /** Org IANA timezone. */
  timezone: string;
  /** Contents of detail.allowed_actions (server-computed; the backend still re-checks on every call). */
  allowed: ReadonlySet<string>;
}

export interface RequestActionProps {
  ctx: RequestActionContext;
}

export interface RequestActionDefinition {
  /** Unique id. For `when: "allowed"` it MUST equal an entry of detail.allowed_actions (e.g. "cancel", "triage"). */
  name: string;
  /** Human label (used for the error boundary message and a11y). */
  label: string;
  component: ComponentType<RequestActionProps>;
  placement: ActionPlacement;
  /**
   * "allowed" (default): render only when `name` is in detail.allowed_actions.
   * "always": render regardless (use for panels that explain why an action is unavailable).
   * Pass `show` for fully custom logic (takes precedence).
   */
  when?: "allowed" | "always";
  show?: (ctx: RequestActionContext) => boolean;
  /** Restrict to roles (defaults to the role set of the map it is registered in). */
  roles?: readonly Role[];
  /** Lower first. Default 100. */
  order?: number;
}
