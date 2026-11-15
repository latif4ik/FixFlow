// OWNER: W3. Staff (dispatcher/admin) panels and actions on the request detail. See ../README.md.
import { AssignmentPanel } from "@/features/dispatch/request/assignment-panel";
import { EstimatePanel } from "@/features/dispatch/request/estimate-panel";
import { CancelRequestAction, CloseRequestAction } from "@/features/dispatch/request/header-actions";
import { TriagePanel } from "@/features/dispatch/request/triage-panel";
import type { RequestActionContext, RequestActionDefinition } from "../types";

const DISPATCH = ["DISPATCHER", "ADMIN"] as const;
const OPEN_FOR_ESTIMATES = ["TRIAGED", "SCHEDULED", "ACCEPTED", "IN_PROGRESS", "BLOCKED", "REOPENED"];
const TERMINAL = ["CLOSED", "CANCELED"];

/** Panels need a loaded detail (status); a partial ctx renders nothing. */
const loaded = (ctx: RequestActionContext) => typeof ctx.detail.status === "string";

/** Assignment panel is visible whenever the request is live, so a dispatcher also sees why assigning is not possible yet. */
const showAssignment = (ctx: RequestActionContext) => loaded(ctx) && !TERMINAL.includes(ctx.detail.status) && ctx.detail.status !== "COMPLETED";
const showEstimate = (ctx: RequestActionContext) => loaded(ctx) && (OPEN_FOR_ESTIMATES.includes(ctx.detail.status) || ctx.detail.estimate != null);
const showTriage = (ctx: RequestActionContext) => loaded(ctx) && !TERMINAL.includes(ctx.detail.status);

export const staffActions: RequestActionDefinition[] = [
  { name: "cancel", label: "Cancel request", component: CancelRequestAction, placement: "header", roles: DISPATCH, order: 20 },
  { name: "close", label: "Close request", component: CloseRequestAction, placement: "header", roles: DISPATCH, order: 10 },
  { name: "assignment", label: "Assignment", component: AssignmentPanel, placement: "main", roles: DISPATCH, show: showAssignment, order: 10 },
  { name: "estimate", label: "Estimate", component: EstimatePanel, placement: "main", roles: DISPATCH, show: showEstimate, order: 20 },
  { name: "triage", label: "Triage", component: TriagePanel, placement: "sidebar", roles: DISPATCH, show: showTriage, order: 10 },
];
