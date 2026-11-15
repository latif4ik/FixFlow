"use client";

import { Sparkles } from "lucide-react";
import Link from "next/link";
import { DataTable, DateTime, EmptyState, PageHeader, PriorityBadge, SlaBadge, StatusBadge } from "@/components/ui";
import { buttonStyles } from "@/components/ui/button";
import type { Column } from "@/components/ui";
import type { Page, RequestListItem, RequestStatus, Schemas } from "@/lib/api/types";
import { formatDuration } from "@/lib/format";
import { useApiQuery } from "@/lib/query/hooks";
import { qk } from "@/lib/query/keys";

type OverdueItem = Schemas["OverdueItem"];
const UNASSIGNED: RequestStatus[] = ["SUBMITTED", "TRIAGED", "REOPENED"];

function RowAction({ id, status, title }: { id: string; status: RequestStatus; title: string }) {
  if (UNASSIGNED.includes(status)) {
    return (
      <Link href={`/requests/${id}#assign`} aria-label={`Smart assign ${title}`} className={buttonStyles({ size: "sm" })}>
        <Sparkles className="size-4" aria-hidden /> Smart assign
      </Link>
    );
  }
  return (
    <Link href={`/requests/${id}`} aria-label={`Open ${title}`} className={buttonStyles({ size: "sm", variant: "secondary" })}>
      Open
    </Link>
  );
}

function idCol<T extends { id: string; display_id: string; title: string }>(): Column<T>[] {
  return [
    {
      key: "req",
      header: "Request",
      className: "min-w-56",
      cell: (r) => (
        <Link href={`/requests/${r.id}`} className="font-medium text-ink hover:underline">
          <span className="font-semibold text-primary-dark">{r.display_id}</span> · {r.title}
        </Link>
      ),
    },
  ];
}

export function OverduePage() {
  const overdue = useApiQuery<{ count: number; items: OverdueItem[]; page: number; page_size: number }>({
    queryKey: (o) => qk.dashboard.overdue(o, { page_size: 50 }),
    path: "/dashboard/overdue",
    query: { page_size: 50 },
  });
  const risk = useApiQuery<Page<RequestListItem>>({
    queryKey: (o) => qk.requests.list(o, { sla_state: ["AT_RISK"], sort: "due", page_size: 50 }),
    path: "/requests",
    query: { sla_state: ["AT_RISK"], sort: "due", page_size: 50 },
  });

  const overdueCols: Column<OverdueItem>[] = [
    ...idCol<OverdueItem>(),
    { key: "property", header: "Property", cell: (r) => r.property.name },
    { key: "priority", header: "Priority", cell: (r) => <PriorityBadge priority={r.priority} /> },
    { key: "status", header: "Status", cell: (r) => <StatusBadge status={r.status} /> },
    {
      key: "late",
      header: "Overdue by",
      cell: (r) => (
        <span className="font-semibold text-danger-dark">
          {formatDuration(r.overdue_by_minutes)}
          <span className="block text-xs font-normal text-muted">
            due <DateTime value={r.sla_due_at} style="short" />
          </span>
        </span>
      ),
    },
    { key: "esc", header: "Escalated", cell: (r) => (r.escalated_at ? <DateTime value={r.escalated_at} style="short" /> : <span className="text-muted">Not yet</span>) },
    { key: "act", header: <span className="sr-only">Action</span>, cell: (r) => <RowAction id={r.id} status={r.status} title={r.display_id} /> },
  ];
  const riskCols: Column<RequestListItem>[] = [
    ...idCol<RequestListItem>(),
    { key: "property", header: "Property", cell: (r) => r.property.name },
    { key: "priority", header: "Priority", cell: (r) => <PriorityBadge priority={r.priority} /> },
    { key: "status", header: "Status", cell: (r) => <StatusBadge status={r.status} /> },
    { key: "sla", header: "SLA", cell: (r) => <SlaBadge state={r.sla_state} dueAt={r.sla_due_at} /> },
    { key: "act", header: <span className="sr-only">Action</span>, cell: (r) => <RowAction id={r.id} status={r.status} title={r.display_id} /> },
  ];

  return (
    <>
      <PageHeader
        title="Overdue and at risk"
        description="Requests past their SLA, most overdue first, and requests about to breach it. Smart assign suggests technician slots."
        actions={
          <Link href="/queue?sla_state=OVERDUE" className={buttonStyles({ variant: "secondary" })}>
            Open in queue
          </Link>
        }
      />
      <div className="flex flex-col gap-6">
        <section aria-labelledby="od-h" className="flex flex-col gap-3">
          <h2 id="od-h" className="font-heading text-lg font-bold">
            Overdue{overdue.data ? ` (${overdue.data.count})` : ""}
          </h2>
          <DataTable
            caption="Overdue requests"
            columns={overdueCols}
            rows={overdue.data?.items}
            rowKey={(r) => r.id}
            loading={overdue.isLoading}
            error={overdue.error}
            onRetry={() => void overdue.refetch()}
            empty={<EmptyState title="Nothing is overdue" description="Every open request is within its SLA." />}
          />
        </section>
        <section aria-labelledby="ar-h" className="flex flex-col gap-3">
          <h2 id="ar-h" className="font-heading text-lg font-bold">
            At risk{risk.data ? ` (${risk.data.total})` : ""}
          </h2>
          <DataTable
            caption="At-risk requests"
            columns={riskCols}
            rows={risk.data?.items}
            rowKey={(r) => r.id}
            loading={risk.isLoading}
            error={risk.error}
            onRetry={() => void risk.refetch()}
            empty={<EmptyState title="Nothing is at risk" description="No request is close to its SLA due time." />}
          />
        </section>
      </div>
    </>
  );
}
