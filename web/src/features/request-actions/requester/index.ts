// OWNER: W2. Requester panels/actions (estimate decision, close/rework, cancel, edit, feedback). See ../README.md.
import { EditRequestAction } from "@/features/requester/edit-request-action";
import { EstimateDecisionPanel } from "@/features/requester/estimate-decision-panel";
import { FeedbackFormPanel } from "@/features/requester/feedback-panel";
import { CancelRequestAction, CloseRequestAction, RequestReworkAction } from "@/features/requester/transition-actions";
import type { RequestActionDefinition } from "../types";

export const requesterActions: RequestActionDefinition[] = [
  // Estimate decisions are not an allowed_actions entry: shown whenever the current estimate awaits approval.
  {
    name: "estimate-decision",
    label: "Estimate decision",
    component: EstimateDecisionPanel,
    placement: "main",
    show: (ctx) => ctx.detail.estimate?.status === "AWAITING_APPROVAL",
    order: 5,
  },
  { name: "close", label: "Close request", component: CloseRequestAction, placement: "header", order: 10 },
  { name: "reopen", label: "Request rework", component: RequestReworkAction, placement: "header", order: 20 },
  { name: "edit", label: "Edit request", component: EditRequestAction, placement: "header", order: 30 },
  { name: "cancel", label: "Cancel request", component: CancelRequestAction, placement: "header", order: 40 },
  // Feedback is not an allowed_actions entry: shown after completion until feedback has been given.
  {
    name: "feedback",
    label: "Satisfaction feedback",
    component: FeedbackFormPanel,
    placement: "main",
    show: (ctx) => (ctx.detail.status === "COMPLETED" || ctx.detail.status === "CLOSED") && !ctx.detail.feedback,
    order: 6,
  },
];
