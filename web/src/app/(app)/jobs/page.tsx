"use client";

import Link from "next/link";
import { EmptyState, ErrorState, InlineNote, LoadingState, PageHeader, Panel, PriorityBadge, StatusBadge, DateTime } from "@/components/ui";
import type { Page, Schemas } from "@/lib/api";
import { useApiQuery } from "@/lib/query/hooks";
import { qk } from "@/lib/query/keys";

// Owner: W1. Technician jobs are read-only on the web; actions live in the Android app.
export default function JobsPage() {
  const q = useApiQuery<Page<Schemas["MyAssignmentItem"]>>({ queryKey: (o) => qk.myAssignments.list(o, {}), path: "/me/assignments" });
  return (
    <>
      <PageHeader title="My jobs" />
      <InlineNote>This is a read-only list. Accepting, starting and completing jobs happens in the FixFlow Android app.</InlineNote>
      <Panel className="mt-4" bodyClassName="p-0">
        {q.isLoading && <LoadingState />}
        {q.isError && <ErrorState error={q.error} onRetry={() => void q.refetch()} />}
        {q.data?.items.length === 0 && <EmptyState title="No jobs assigned" description="Assigned jobs appear here." />}
        <ul>
          {q.data?.items.map((a) => (
            <li key={a.assignment_id} className="flex flex-wrap items-center gap-3 border-b border-border px-5 py-4 last:border-0">
              <div className="min-w-0 flex-1">
                <Link href={`/requests/${a.request.id}`} className="font-semibold text-ink hover:underline">
                  {a.request.display_id} · {a.request.title}
                </Link>
                <p className="text-[13px] text-muted">
                  {a.request.property.name} · <DateTime value={a.appointment.start_at} style="short" />
                </p>
              </div>
              <PriorityBadge priority={a.request.priority} />
              <StatusBadge status={a.request.status} />
            </li>
          ))}
        </ul>
      </Panel>
    </>
  );
}
