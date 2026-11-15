"use client";

import { AlertTriangle, TimerOff, UserRound } from "lucide-react";
import Link from "next/link";
import { buttonStyles, EmptyState, ErrorState, PageHeader, Panel, Skeleton, StatusBadge } from "@/components/ui";
import type { Page, RequestListItem, Schemas } from "@/lib/api";
import { useOrgTimezone } from "@/lib/auth";
import { formatDateTime, formatDuration } from "@/lib/format";
import { qk, useApiQuery } from "@/lib/query";
import { cn } from "@/lib/cn";
import { DayTimeline, useTodaySchedule } from "./day-timeline";
import { useReportFilters } from "./filters";
import { DailyChart, DistributionChart, EstimatesCard, ReportFilterBar, StatusCounts, UtilizationCard, useDaily, useSummary } from "./report-widgets";
import { formatDayLong, formatYmd } from "./tz";

type OverdueQueue = Schemas["OverdueQueue"];

const UNASSIGNED = new Set(["SUBMITTED", "TRIAGED", "REOPENED"]);

function Kpi({ label, value, note }: { label: string; value: React.ReactNode; note?: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5">
      <dt className="text-[13px] text-muted">{label}</dt>
      <dd className="font-heading text-[28px] font-extrabold leading-tight tracking-tight text-ink">{value}</dd>
      {note && <dd className="text-[12px] text-muted">{note}</dd>}
    </div>
  );
}

export function DashboardPage() {
  const tz = useOrgTimezone();
  const { filters, setFilter, clear } = useReportFilters();
  const summary = useSummary(filters);
  const daily = useDaily(14);
  const overdue = useApiQuery<OverdueQueue>({ queryKey: (o) => qk.dashboard.overdue(o, { page_size: 3 }), path: "/dashboard/overdue", query: { page_size: 3 } });
  const atRisk = useApiQuery<Page<RequestListItem>>({
    queryKey: (o) => qk.requests.list(o, { sla_state: "AT_RISK", page_size: 100 }),
    path: "/requests",
    query: { sla_state: "AT_RISK", page_size: 100 },
  });
  const unassigned = useApiQuery<Page<RequestListItem>>({
    queryKey: (o) => qk.requests.list(o, { status: "TRIAGED", page_size: 1 }),
    path: "/requests",
    query: { status: "TRIAGED", page_size: 1 },
  });
  const schedule = useTodaySchedule();

  const overdueCount = overdue.data?.count;
  const unassignedCount = unassigned.data?.total;
  const todays = schedule.data?.technicians.flatMap((t) => t.assignments) ?? [];
  const inProgress = todays.filter((a) => a.request_status === "IN_PROGRESS").length;
  const nextDue = atRisk.data?.items
    .map((r) => (r.sla_due_at ? new Date(r.sla_due_at).getTime() : null))
    .filter((t): t is number => t !== null && t > schedule.now)
    .sort((a, b) => a - b)[0];
  const sentence =
    overdueCount === undefined || unassignedCount === undefined
      ? "Loading the day's numbers."
      : `${overdueCount === 1 ? "1 request is" : `${overdueCount} requests are`} overdue and ${unassignedCount} ${unassignedCount === 1 ? "is" : "are"} waiting for a technician.`;
  const range = summary.data?.range;
  const rangeText = range ? `${formatYmd(range.from_date)} to ${formatYmd(range.to_date)}` : undefined;

  return (
    <div className="flex flex-col gap-5">
      <PageHeader title={schedule.now ? formatDayLong(schedule.now, tz) : "Dashboard"} description={sentence} className="mb-0" />
      <ReportFilterBar filters={filters} setFilter={setFilter} clear={clear} range={range} />

      <div className="grid gap-5 lg:grid-cols-3">
        <Panel
          className="lg:col-span-2"
          title={
            <span className="flex items-center gap-3">
              <span aria-hidden className="flex size-9 items-center justify-center rounded-md bg-danger-tint text-danger">
                <TimerOff className="size-5" />
              </span>
              Overdue and escalations
            </span>
          }
          actions={overdueCount !== undefined && <span className="rounded-md bg-danger-tint px-2.5 py-1 text-[13px] font-semibold text-danger-dark">{overdueCount} past SLA due time</span>}
        >
          {overdue.error ? (
            <ErrorState error={overdue.error} onRetry={() => overdue.refetch()} />
          ) : overdue.isLoading || !overdue.data ? (
            <Skeleton className="h-32 w-full" />
          ) : overdue.data.items.length === 0 ? (
            <EmptyState title="Nothing is overdue" description="Every request is within its SLA due time." />
          ) : (
            <div className="flex flex-col gap-3">
              <ul className="flex flex-col">
                {overdue.data.items.map((r) => (
                  <li key={r.id} className="flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-border py-3 first:border-t-0">
                    <div className="w-28 shrink-0 leading-tight">
                      <p className="text-[12px] text-muted">Overdue by</p>
                      <p className="font-heading text-base font-bold text-danger">{formatDuration(r.overdue_by_minutes)}</p>
                    </div>
                    <div className="flex min-w-0 flex-1 basis-60 flex-col gap-1">
                      <p className="text-sm">
                        <Link href={`/requests/${r.id}`} className="font-semibold text-primary hover:text-primary-dark">
                          {r.display_id}
                        </Link>{" "}
                        {r.title}
                      </p>
                      <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px] text-muted">
                        <span>
                          {r.property.name} · {r.category.name}
                        </span>
                        <StatusBadge status={r.status} />
                      </p>
                    </div>
                    {UNASSIGNED.has(r.status) ? (
                      <Link href={`/requests/${r.id}#assign`} className={cn(buttonStyles({ size: "md" }))}>
                        Smart assign <span className="sr-only">{r.display_id}</span>
                      </Link>
                    ) : (
                      <Link href={`/requests/${r.id}`} className={cn(buttonStyles({ variant: "secondary", size: "md" }))}>
                        Open <span className="sr-only">{r.display_id}</span>
                      </Link>
                    )}
                  </li>
                ))}
              </ul>
              <Link href="/overdue" className="text-sm font-semibold text-primary hover:text-primary-dark">
                Review all {overdue.data.count} overdue requests
              </Link>
            </div>
          )}
        </Panel>

        <div className="flex flex-col gap-5">
          <Panel>
            <div className="flex gap-4">
              <span className="min-w-12 font-heading text-[44px] font-extrabold leading-none text-warning-dark">{atRisk.data ? atRisk.data.total : "-"}</span>
              <div className="flex flex-col gap-1.5">
                <h2 className="flex items-center gap-1.5 text-[15px] font-semibold">
                  <AlertTriangle className="size-4 text-warning-dark" aria-hidden /> At risk
                </h2>
                <p className="text-[13px] text-muted">
                  Close to their SLA due time.{" "}
                  {nextDue ? `The next one is due in ${formatDuration(Math.max(0, Math.round((nextDue - schedule.now) / 60_000)))}.` : ""}
                </p>
                <Link href="/queue?sla_state=AT_RISK" className="text-sm font-semibold text-primary hover:text-primary-dark">
                  See at-risk requests
                </Link>
              </div>
            </div>
          </Panel>
          <Panel>
            <div className="flex gap-4">
              <span className="min-w-12 font-heading text-[44px] font-extrabold leading-none text-ink">{unassignedCount ?? "-"}</span>
              <div className="flex flex-col items-start gap-1.5">
                <h2 className="flex items-center gap-1.5 text-[15px] font-semibold">
                  <UserRound className="size-4" aria-hidden /> Unassigned
                </h2>
                <p className="text-[13px] text-muted">Triaged and waiting for a technician.</p>
                <Link href="/queue?status=TRIAGED" className={buttonStyles({ size: "md" })}>
                  Assign technicians
                </Link>
              </div>
            </div>
          </Panel>
        </div>
      </div>

      <Panel bodyClassName="p-0" as="section">
        {summary.error ? (
          <div className="p-5">
            <ErrorState error={summary.error} onRetry={() => summary.refetch()} />
          </div>
        ) : (
          <dl aria-label="Totals" className="grid grid-cols-[repeat(auto-fit,minmax(min(200px,100%),1fr))] gap-x-8 gap-y-4 px-6 py-5">
            <Kpi label="Open requests" value={summary.data?.open_requests ?? "-"} note="All active statuses" />
            <Kpi label="Today's appointments" value={schedule.data ? todays.length : "-"} note={schedule.data ? `${inProgress} in progress now` : undefined} />
            <Kpi label="Upcoming appointments" value={summary.data?.upcoming_appointments ?? "-"} note="Scheduled from now on" />
            <Kpi label="Completed in range" value={summary.data?.completed_in_range ?? "-"} note={rangeText} />
          </dl>
        )}
      </Panel>

      <DayTimeline schedule={schedule.data} loading={schedule.isLoading} error={schedule.error} onRetry={() => schedule.refetch()} today={schedule.today} now={schedule.now} />

      <div className="grid gap-5 lg:grid-cols-2">
        <DailyChart data={daily.data} loading={daily.isLoading} error={daily.error} onRetry={() => daily.refetch()} />
        <DistributionChart filters={filters} rangeText={rangeText} />
      </div>

      <div className="grid gap-5 lg:grid-cols-3">
        <UtilizationCard summary={summary.data} loading={summary.isLoading} showLink />
        <EstimatesCard summary={summary.data} loading={summary.isLoading} />
        <StatusCounts summary={summary.data} loading={summary.isLoading} />
      </div>

      <p className="text-[12px] text-muted">
        {schedule.now ? `As of ${formatDateTime(schedule.now, tz, "datetime")} (${tz})` : ""}
        {rangeText ? ` · Report range ${rangeText}` : ""}
      </p>
    </div>
  );
}
