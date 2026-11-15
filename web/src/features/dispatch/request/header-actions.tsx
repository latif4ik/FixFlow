"use client";

import { CheckCheck, Ban } from "lucide-react";
import { useState } from "react";
import { Button, ConfirmDialog } from "@/components/ui";
import { useApiMutation } from "@/lib/query/hooks";
import { qk } from "@/lib/query/keys";
import type { RequestActionProps } from "@/features/request-actions/types";

function useReasonAction(ctx: RequestActionProps["ctx"], verb: "cancel" | "close", success: string) {
  return useApiMutation<unknown, { reason: string }>({
    request: (v) => ({ path: `/requests/${ctx.requestId}/${verb}`, body: v }),
    idempotent: true,
    invalidate: (o) => [qk.requests.detail(o, ctx.requestId), qk.requests.all(o), qk.schedule.all(o), qk.dashboard.all(o)],
    successMessage: success,
  });
}

export function CancelRequestAction({ ctx }: RequestActionProps) {
  const [open, setOpen] = useState(false);
  const m = useReasonAction(ctx, "cancel", "Request canceled.");
  return (
    <>
      <Button variant="secondary" onClick={() => setOpen(true)}>
        <Ban className="size-4" aria-hidden /> Cancel request
      </Button>
      <ConfirmDialog
        open={open}
        onOpenChange={setOpen}
        title={`Cancel ${ctx.detail.display_id}?`}
        description="Any assignment is released, the technician and requester are notified, and the request cannot be reopened."
        confirmLabel="Cancel request"
        cancelLabel="Keep request"
        reason={{ label: "Reason (required)", minLength: 5 }}
        onConfirm={(reason) => m.mutateAsync({ reason })}
      />
    </>
  );
}

export function CloseRequestAction({ ctx }: RequestActionProps) {
  const [open, setOpen] = useState(false);
  const m = useReasonAction(ctx, "close", "Request closed.");
  return (
    <>
      <Button variant="secondary" onClick={() => setOpen(true)}>
        <CheckCheck className="size-4" aria-hidden /> Close request
      </Button>
      <ConfirmDialog
        open={open}
        onOpenChange={setOpen}
        title={`Close ${ctx.detail.display_id}?`}
        description="Closing is final: the request leaves the open queue and its SLA stops."
        confirmLabel="Close request"
        cancelLabel="Keep open"
        reason={{ label: "Reason (required)", minLength: 5 }}
        onConfirm={(reason) => m.mutateAsync({ reason })}
      />
    </>
  );
}
