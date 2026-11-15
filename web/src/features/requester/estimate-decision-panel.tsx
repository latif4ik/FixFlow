"use client";

import { estimateStatusLabel } from "@/lib/labels";
import { Check, X } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Badge, Button, DateTime, InlineNote, Money, Panel, toast } from "@/components/ui";
import type { Schemas } from "@/lib/api/types";
import { formatDuration } from "@/lib/format";
import { useApiMutation, useApiQuery } from "@/lib/query/hooks";
import { qk } from "@/lib/query/keys";
import type { RequestActionProps } from "@/features/request-actions/types";
import { isApiError } from "@/lib/api/client";
import { ReasonDialog } from "./reason-dialog";

type Estimate = Schemas["EstimateOut"];
type Decision = { version: number; decision: "APPROVE" | "REJECT"; reason?: string };

const STATUS_LABEL: Record<string, string> = {
  DRAFT: "Draft",
  AWAITING_APPROVAL: "Awaiting your decision",
  APPROVED: "Approved",
  REJECTED: "Rejected",
  WITHDRAWN: "Withdrawn",
  SUPERSEDED: "Superseded",
};

/** Requester decision on the estimate that currently awaits approval. */
export function EstimateDecisionPanel({ ctx }: RequestActionProps) {
  const current = ctx.detail.estimate;
  const [rejecting, setRejecting] = useState(false);
  const queryClient = useQueryClient();

  const history = useApiQuery<Estimate[]>({
    queryKey: (o) => qk.requests.estimates(o, ctx.requestId),
    path: `/requests/${ctx.requestId}/estimates`,
  });

  const decide = useApiMutation<unknown, Decision>({
    request: (v) => ({ path: `/estimates/${current?.id}/decision`, body: v }),
    idempotent: true,
    invalidate: (orgId) => [qk.requests.detail(orgId, ctx.requestId), qk.requests.estimates(orgId, ctx.requestId), qk.requests.all(orgId), qk.estimates.all(orgId)],
    successMessage: (_d, v) => (v.decision === "APPROVE" ? "Estimate approved." : "Estimate rejected. The team will prepare a revision."),
    errorMessage: false,
    onError: (e) => {
      if (isApiError(e) && e.status === 409) {
        // Already decided or a newer version exists: reload the latest state and explain.
        toast.error("This estimate changed — review the latest version");
        setRejecting(false);
        if (ctx.orgId) {
          void queryClient.invalidateQueries({ queryKey: qk.requests.detail(ctx.orgId, ctx.requestId) });
          void queryClient.invalidateQueries({ queryKey: qk.requests.estimates(ctx.orgId, ctx.requestId) });
        }
      } else if (isApiError(e) && e.status !== 401) {
        toast.error(e.message);
      }
    },
  });

  if (!current) return null;
  const awaiting = current.status === "AWAITING_APPROVAL";
  const full = history.data?.find((e) => e.id === current.id);
  const previous = (history.data ?? []).filter((e) => e.id !== current.id).sort((a, b) => b.version - a.version);

  return (
    <Panel
      title="Estimate for your approval"
      actions={<Badge tone={awaiting ? "warning" : "neutral"}>{`Version ${current.version} · ${STATUS_LABEL[current.status] ?? estimateStatusLabel(current.status)}`}</Badge>}
    >
      <p className="mb-3 text-[13px] text-muted">This is an estimate of the cost, not a payment or an invoice. Nothing is charged by approving it.</p>
      <ul className="divide-y divide-border text-sm" aria-label="Estimate lines">
        {current.lines.map((l) => (
          <li key={l.id} className="flex items-start justify-between gap-3 py-2">
            <span>
              {l.description}
              <span className="block text-[13px] text-muted">
                {Number(l.quantity)} × <Money minor={l.unit_price_minor} currency={current.currency} />
              </span>
            </span>
            <Money minor={l.line_total_minor} currency={current.currency} />
          </li>
        ))}
      </ul>
      <dl className="mt-3 space-y-1 border-t border-border pt-3 text-sm">
        <div className="flex justify-between">
          <dt>Labor ({formatDuration(current.labor_minutes)})</dt>
          <dd>
            <Money minor={current.labor_cost_minor} currency={current.currency} />
          </dd>
        </div>
        <div className="flex justify-between">
          <dt>Materials</dt>
          <dd>
            <Money minor={current.materials_total_minor} currency={current.currency} />
          </dd>
        </div>
        <div className="flex justify-between border-t border-border pt-2 font-heading text-base font-bold text-ink">
          <dt>Total estimate</dt>
          <dd>
            <Money minor={current.total_minor} currency={current.currency} />
          </dd>
        </div>
      </dl>
      {full?.notes && <p className="mt-3 rounded-md bg-canvas px-3 py-2 text-sm text-text">Note from the team: {full.notes}</p>}

      {awaiting ? (
        <div className="mt-4 flex flex-wrap gap-2">
          <Button loading={decide.isPending} onClick={() => decide.mutate({ version: current.version, decision: "APPROVE" })}>
            <Check className="size-4" aria-hidden /> Approve estimate
          </Button>
          <Button variant="secondary" disabled={decide.isPending} onClick={() => setRejecting(true)}>
            <X className="size-4" aria-hidden /> Reject estimate
          </Button>
        </div>
      ) : (
        <div className="mt-4">
          <InlineNote>{`This estimate is ${(STATUS_LABEL[current.status] ?? estimateStatusLabel(current.status)).toLowerCase()}.`}</InlineNote>
        </div>
      )}

      {previous.length > 0 && (
        <details className="mt-4 text-sm">
          <summary className="cursor-pointer font-semibold text-ink">Earlier versions ({previous.length})</summary>
          <ul className="mt-2 space-y-2">
            {previous.map((e) => (
              <li key={e.id} className="rounded-md border border-border px-3 py-2">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="font-semibold">Version {e.version}</span>
                  <Badge tone="neutral">{STATUS_LABEL[e.status] ?? estimateStatusLabel(e.status)}</Badge>
                </div>
                <div className="mt-1 text-[13px] text-muted">
                  <Money minor={e.total_minor} currency={e.currency} />
                  {e.decided_at && (
                    <>
                      {" · decided "}
                      <DateTime value={e.decided_at} style="short" />
                    </>
                  )}
                </div>
                {e.decision_reason && <p className="mt-1 text-[13px] text-text">Reason: {e.decision_reason}</p>}
              </li>
            ))}
          </ul>
        </details>
      )}

      <ReasonDialog
        open={rejecting}
        onOpenChange={setRejecting}
        title="Reject this estimate?"
        description={`Version ${current.version}. The team will see your reason and can send a revised estimate.`}
        label="Why are you rejecting it?"
        minLength={5}
        confirmLabel="Reject estimate"
        cancelLabel="Back"
        destructive
        onSubmit={(reason) => decide.mutateAsync({ version: current.version, decision: "REJECT", reason })}
      />
    </Panel>
  );
}
