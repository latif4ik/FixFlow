"use client";

import { CheckCheck, RotateCcw, XCircle } from "lucide-react";
import { useState } from "react";
import { Button, ConfirmDialog } from "@/components/ui";
import type { RequestDetail } from "@/lib/api/types";
import { useApiMutation } from "@/lib/query/hooks";
import { qk } from "@/lib/query/keys";
import type { RequestActionProps } from "@/features/request-actions/types";
import { ReasonDialog } from "./reason-dialog";

function useTransition(ctx: RequestActionProps["ctx"], action: "close" | "reopen" | "cancel", successMessage: string) {
  return useApiMutation<RequestDetail, { reason?: string }>({
    request: (v) => ({ path: `/requests/${ctx.requestId}/${action}`, body: v.reason ? { reason: v.reason } : {} }),
    idempotent: true,
    invalidate: (orgId) => [qk.requests.detail(orgId, ctx.requestId), qk.requests.all(orgId), qk.dashboard.all(orgId)],
    successMessage,
  });
}

/** Requester closes a COMPLETED request (accepts the work). */
export function CloseRequestAction({ ctx }: RequestActionProps) {
  const [open, setOpen] = useState(false);
  const m = useTransition(ctx, "close", "Request closed. Thank you!");
  return (
    <>
      <Button onClick={() => setOpen(true)}>
        <CheckCheck className="size-4" aria-hidden /> Close request
      </Button>
      <ConfirmDialog
        open={open}
        onOpenChange={setOpen}
        title="Close this request?"
        description="Confirm the work is done to your satisfaction. A closed request can no longer be reopened."
        confirmLabel="Close request"
        cancelLabel="Not yet"
        destructive={false}
        onConfirm={() => m.mutateAsync({})}
      />
    </>
  );
}

/** Requester asks for rework on a COMPLETED request (COMPLETED -> REOPENED). */
export function RequestReworkAction({ ctx }: RequestActionProps) {
  const [open, setOpen] = useState(false);
  const m = useTransition(ctx, "reopen", "Rework requested. The team has been notified.");
  return (
    <>
      <Button variant="secondary" onClick={() => setOpen(true)}>
        <RotateCcw className="size-4" aria-hidden /> Request rework
      </Button>
      <ReasonDialog
        open={open}
        onOpenChange={setOpen}
        title="Request rework"
        description="Tell us what is still wrong so the team can fix it."
        label="What still needs fixing?"
        minLength={5}
        confirmLabel="Request rework"
        cancelLabel="Cancel"
        onSubmit={(reason) => m.mutateAsync({ reason })}
      />
    </>
  );
}

/** Requester cancels their own SUBMITTED request (destructive: always confirmed). */
export function CancelRequestAction({ ctx }: RequestActionProps) {
  const [open, setOpen] = useState(false);
  const m = useTransition(ctx, "cancel", "Request canceled.");
  return (
    <>
      <Button variant="secondary" onClick={() => setOpen(true)}>
        <XCircle className="size-4" aria-hidden /> Cancel request
      </Button>
      <ReasonDialog
        open={open}
        onOpenChange={setOpen}
        title="Cancel this request?"
        description="The request will be withdrawn and nobody will be sent. This cannot be undone."
        label="Reason (optional)"
        confirmLabel="Cancel request"
        cancelLabel="Keep request"
        destructive
        onSubmit={(reason) => m.mutateAsync({ reason })}
      />
    </>
  );
}
