"use client";

import { useMemo } from "react";
import { ErrorState, LoadingState, PageHeader, StatusBadge, PriorityBadge, SlaBadge } from "@/components/ui";
import type { RequestDetail } from "@/lib/api/types";
import type { ApiError } from "@/lib/api/client";
import { useAuth } from "@/lib/auth/auth-context";
import { useApiQuery } from "@/lib/query/hooks";
import { qk } from "@/lib/query/keys";
import { RequestActionSlot } from "@/features/request-actions/registry";
import type { RequestActionContext } from "@/features/request-actions/registry";
import { Activity, Attachments, EstimateSummaryPanel, FactsPanel, FeedbackPanel, MaterialsPanel, MessagesPanel } from "./sections";
import { StatusStepper } from "./status-stepper";

/**
 * Shared request detail (requester AND staff). Owner: W1.
 * Role-specific actions render through the registry (src/features/request-actions).
 */
export function RequestDetailPage({ requestId }: { requestId: string }) {
  const { orgId, role, timezone } = useAuth();
  const q = useApiQuery<RequestDetail>({
    queryKey: (o) => qk.requests.detail(o, requestId),
    path: `/requests/${requestId}`,
  });

  const ctx = useMemo<RequestActionContext | null>(
    () => (q.data && orgId && role ? { requestId, detail: q.data, orgId, role, timezone, allowed: new Set(q.data.allowed_actions) } : null),
    [q.data, orgId, role, timezone, requestId],
  );

  if (q.isLoading) return <LoadingState label="Loading request" />;
  if (q.isError) {
    const e: ApiError = q.error;
    return (
      <ErrorState
        title={e.status === 404 || e.status === 403 ? "Request not found" : "Could not load the request"}
        error={e.status === 404 || e.status === 403 ? { message: "It may not exist, or you may not have access to it.", requestId: e.requestId } : e}
        onRetry={() => void q.refetch()}
      />
    );
  }
  if (!q.data || !ctx || !role) return null;
  const d = q.data;
  const isStaff = role !== "REQUESTER";
  const listHref = role === "REQUESTER" ? "/requests" : role === "TECHNICIAN" ? "/jobs" : "/queue";

  return (
    <>
      <PageHeader
        breadcrumb={[{ label: role === "REQUESTER" ? "My requests" : role === "TECHNICIAN" ? "My jobs" : "Request queue", href: listHref }, { label: d.display_id }]}
        title={
          <span className="flex flex-col gap-1">
            <span className="text-sm font-semibold text-muted">{d.display_id}</span>
            {d.title}
          </span>
        }
        actions={<RequestActionSlot placement="header" ctx={ctx} className="flex flex-wrap items-center gap-2" />}
      />
      <div className="mb-5 flex flex-wrap items-center gap-2">
        <StatusBadge status={d.status} />
        <PriorityBadge priority={d.priority} />
        {d.sla_state && d.status !== "CLOSED" && d.status !== "CANCELED" && (
          <SlaBadge state={d.sla_state} dueAt={d.sla?.due_at ?? d.sla_due_at} remainingMinutes={d.sla?.remaining_minutes} overdueByMinutes={d.sla?.overdue_by_minutes} />
        )}
      </div>
      <StatusStepper status={d.status} />

      <div className="mt-5 grid gap-5 lg:grid-cols-[minmax(0,1fr)_380px]">
        <div className="flex min-w-0 flex-col gap-5">
          <FactsPanel detail={d} role={role} />
          <RequestActionSlot placement="main" ctx={ctx} className="flex flex-col gap-5" />
          <MessagesPanel detail={d} requestId={requestId} role={role} />
          <Attachments detail={d} />
          {isStaff && <MaterialsPanel detail={d} />}
          <FeedbackPanel detail={d} />
        </div>
        <aside aria-label="Request side panels" className="flex min-w-0 flex-col gap-5">
          <RequestActionSlot placement="sidebar" ctx={ctx} className="flex flex-col gap-5" />
          <EstimateSummaryPanel detail={d} />
          <Activity detail={d} />
        </aside>
      </div>
    </>
  );
}
