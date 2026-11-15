"use client";

import { DataTable, ErrorState, Panel } from "@/components/ui";
import type { Column } from "@/components/ui";
import type { Schemas } from "@/lib/api";
import { useReportFilters } from "@/features/dashboard/filters";
import { DailyChart, DistributionChart, EstimatesCard, ReportFilterBar, StatusCounts, UtilizationCard, useDaily, useSummary } from "@/features/dashboard/report-widgets";
import { formatYmd } from "@/features/dashboard/tz";
import { AdminPage } from "./shared";

type TechUtil = Schemas["TechnicianUtilization"];

function pct(v: number | null) {
  return v === null ? "n/a" : `${v}%`;
}

export function ReportsPage() {
  const { filters, setFilter, clear } = useReportFilters();
  const summary = useSummary(filters);
  const daily = useDaily(14);
  const s = summary.data;
  const range = s?.range;
  const rangeText = range ? `${formatYmd(range.from_date)} to ${formatYmd(range.to_date)}` : undefined;

  const columns: Column<TechUtil>[] = [
    { key: "name", header: "Technician", cell: (t) => <strong className="text-ink">{t.name}</strong> },
    { key: "planned", header: "Planned (min)", cell: (t) => <span className="tabular-nums">{t.planned_minutes}</span> },
    { key: "avail", header: "Available (min)", cell: (t) => <span className="tabular-nums">{t.available_minutes}</span> },
    {
      key: "pct",
      header: "Utilization",
      cell: (t) => (
        <span className="tabular-nums">
          {pct(t.percent_capped)}
          {t.percent !== null && t.percent > 100 && <span className="ml-1 text-[12px] text-warning-dark">(raw {t.percent}%)</span>}
        </span>
      ),
    },
  ];

  return (
    <AdminPage title="Reports" description="SLA and operations numbers for the selected range. Figures come straight from the server.">
      <ReportFilterBar filters={filters} setFilter={setFilter} clear={clear} range={range} />
      {summary.error && <ErrorState error={summary.error} onRetry={() => summary.refetch()} />}
      <Panel title="Summary" actions={rangeText && <span className="text-[13px] text-muted">{rangeText}</span>}>
        <dl className="grid grid-cols-[repeat(auto-fit,minmax(170px,1fr))] gap-x-8 gap-y-4">
          {[
            ["Open requests", s?.open_requests],
            ["Overdue requests", s?.overdue_requests],
            ["Upcoming appointments", s?.upcoming_appointments],
            ["Completed in range", s?.completed_in_range],
          ].map(([label, value]) => (
            <div key={String(label)}>
              <dt className="text-[13px] text-muted">{label}</dt>
              <dd className="font-heading text-[28px] font-extrabold leading-tight text-ink">{value ?? "-"}</dd>
            </div>
          ))}
        </dl>
      </Panel>
      <div className="grid gap-5 lg:grid-cols-2">
        <UtilizationCard summary={s} loading={summary.isLoading} />
        <EstimatesCard summary={s} loading={summary.isLoading} />
      </div>
      <Panel title="Utilization by technician" bodyClassName="p-0">
        <DataTable caption="Utilization by technician" columns={columns} rows={s?.technician_utilization.per_technician} rowKey={(t) => t.membership_id} loading={summary.isLoading} />
      </Panel>
      <StatusCounts summary={s} loading={summary.isLoading} />
      <div className="grid gap-5 lg:grid-cols-2">
        <DailyChart data={daily.data} loading={daily.isLoading} error={daily.error} onRetry={() => daily.refetch()} />
        <DistributionChart filters={filters} rangeText={rangeText} />
      </div>
    </AdminPage>
  );
}
