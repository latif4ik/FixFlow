"use client";

import { Info, Wallet } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip as RTooltip, XAxis, YAxis } from "recharts";
import type { TooltipContentProps } from "recharts";
import { Badge, Button, EmptyState, ErrorState, FilterBar, Input, Label, Money, Panel, Select, Skeleton, STATUS_META } from "@/components/ui";
import { REQUEST_STATUSES } from "@/lib/api";
import type { Page, Schemas } from "@/lib/api";
import { qk, useApiQuery } from "@/lib/query";
import type { ReportFilters } from "./filters";
import { formatYmd } from "./tz";

export type ReportSummary = Schemas["ReportSummary"];
export type DailyPoint = Schemas["DailyPoint"];
export type DistributionItem = Schemas["DistributionItem"];

const params = (f: ReportFilters) => ({ from: f.from, to: f.to, category_id: f.category_id, technician_id: f.technician_id });

export function useSummary(f: ReportFilters) {
  return useApiQuery<ReportSummary>({ queryKey: (o) => qk.reports.summary(o, params(f)), path: "/reports/summary", query: params(f) });
}
export function useDaily(days = 14) {
  return useApiQuery<DailyPoint[]>({ queryKey: (o) => qk.reports.daily(o, { days }), path: "/reports/daily", query: { days } });
}
export function useDistribution(by: "priority" | "category", f: ReportFilters) {
  const p = { by, ...params(f) };
  return useApiQuery<DistributionItem[]>({ queryKey: (o) => qk.reports.distribution(o, p), path: "/reports/distribution", query: p });
}

/* ---------------- filters ---------------- */

export function ReportFilterBar({
  filters,
  setFilter,
  clear,
  range,
}: {
  filters: ReportFilters;
  setFilter: (k: keyof ReportFilters, v: string) => void;
  clear: () => void;
  range?: ReportSummary["range"];
}) {
  const cats = useApiQuery<Page<Schemas["CategoryOut"]>>({ queryKey: (o) => qk.categories.list(o, { all: true }), path: "/categories", query: { include_disabled: true, page_size: 100 } });
  const techs = useApiQuery<Page<Schemas["TechnicianOut"]>>({ queryKey: (o) => qk.technicians.list(o, { all: true }), path: "/technicians", query: { page_size: 100 } });
  const from = filters.from ?? range?.from_date ?? "";
  const to = filters.to ?? range?.to_date ?? "";
  const hasFilters = Object.keys(filters).length > 0;
  return (
    <FilterBar label="Report filters">
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="rf-from">From</Label>
        <Input id="rf-from" type="date" value={from} max={to || undefined} onChange={(e) => setFilter("from", e.target.value)} className="w-40" />
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="rf-to">To</Label>
        <Input id="rf-to" type="date" value={to} min={from || undefined} onChange={(e) => setFilter("to", e.target.value)} className="w-40" />
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="rf-cat">Category</Label>
        <Select id="rf-cat" value={filters.category_id ?? ""} onChange={(e) => setFilter("category_id", e.target.value)} className="w-48">
          <option value="">All categories</option>
          {cats.data?.items.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </Select>
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="rf-tech">Technician</Label>
        <Select id="rf-tech" value={filters.technician_id ?? ""} onChange={(e) => setFilter("technician_id", e.target.value)} className="w-56">
          <option value="">All technicians</option>
          {techs.data?.items.map((t) => (
            <option key={t.membership_id} value={t.membership_id}>
              {t.full_name}
            </option>
          ))}
        </Select>
      </div>
      {hasFilters && (
        <Button variant="ghost" onClick={clear}>
          Reset filters
        </Button>
      )}
    </FilterBar>
  );
}

/* ---------------- charts ---------------- */

const COLORS = { new: "var(--color-primary)", completed: "var(--color-warning-dark)" };

type TipProps = TooltipContentProps<number | string | readonly (number | string)[], number | string>;

function DailyTooltip({ active, payload, label }: TipProps) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-md border border-border bg-surface px-3 py-2 text-[13px] shadow-pop">
      <p className="font-semibold text-ink">{formatYmd(String(label))}</p>
      {payload.map((p) => (
        <p key={String(p.name)} className="text-text">
          {String(p.name)}: <strong>{p.value}</strong> requests
        </p>
      ))}
    </div>
  );
}

export function DailyChart({ data, loading, error, onRetry }: { data?: DailyPoint[]; loading?: boolean; error?: { message: string } | null; onRetry?: () => void }) {
  const totalNew = data?.reduce((a, d) => a + d.new_requests, 0) ?? 0;
  const totalDone = data?.reduce((a, d) => a + d.completed_requests, 0) ?? 0;
  const first = data?.[0]?.date;
  const last = data?.[data.length - 1]?.date;
  const rangeText = first && last ? `${formatYmd(first)} to ${formatYmd(last)}` : "last 14 days";
  return (
    <Panel title="New and completed requests" actions={<span className="text-[13px] text-muted">Per day, last 14 days ({rangeText})</span>}>
      {error ? (
        <ErrorState error={error} onRetry={onRetry} />
      ) : loading || !data ? (
        <Skeleton className="h-56 w-full" />
      ) : (
        <figure aria-label="New and completed requests per day">
          <ul className="mb-3 flex flex-wrap gap-x-6 gap-y-1 text-sm" aria-label="Legend with totals for the range">
            <li className="flex items-center gap-2">
              <svg width="22" height="8" aria-hidden>
                <line x1="0" y1="4" x2="22" y2="4" stroke={COLORS.new} strokeWidth="3" />
              </svg>
              <span>
                New requests: <strong>{totalNew}</strong> in range
              </span>
            </li>
            <li className="flex items-center gap-2">
              <svg width="22" height="8" aria-hidden>
                <line x1="0" y1="4" x2="22" y2="4" stroke={COLORS.completed} strokeWidth="3" strokeDasharray="5 3" />
              </svg>
              <span>
                Completed: <strong>{totalDone}</strong> in range
              </span>
            </li>
          </ul>
          <div aria-hidden className="h-56 w-full">
            <ResponsiveContainer width="100%" height="100%" initialDimension={{ width: 640, height: 224 }}>
              <LineChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: -12 }}>
                <CartesianGrid stroke="var(--color-border)" vertical={false} />
                <XAxis dataKey="date" tickFormatter={(v: string) => formatYmd(v)} tick={{ fontSize: 12, fill: "var(--color-muted)" }} interval="preserveStartEnd" />
                <YAxis allowDecimals={false} tick={{ fontSize: 12, fill: "var(--color-muted)" }} label={{ value: "requests", angle: -90, position: "insideLeft", fontSize: 12, fill: "var(--color-muted)" }} />
                <RTooltip content={(p: TipProps) => <DailyTooltip {...p} />} />
                <Line type="monotone" dataKey="new_requests" name="New requests" stroke={COLORS.new} strokeWidth={2.5} dot={{ r: 3 }} />
                <Line type="monotone" dataKey="completed_requests" name="Completed" stroke={COLORS.completed} strokeWidth={2.5} strokeDasharray="5 3" dot={{ r: 3 }} />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <table className="sr-only">
            <caption>New and completed requests per day, {rangeText}</caption>
            <thead>
              <tr>
                <th scope="col">Date</th>
                <th scope="col">New requests</th>
                <th scope="col">Completed requests</th>
              </tr>
            </thead>
            <tbody>
              {data.map((d) => (
                <tr key={d.date}>
                  <th scope="row">{d.date}</th>
                  <td>{d.new_requests}</td>
                  <td>{d.completed_requests}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </figure>
      )}
    </Panel>
  );
}

function DistTooltip({ active, payload }: TipProps) {
  if (!active || !payload?.length) return null;
  const p = payload[0]!;
  return (
    <div className="rounded-md border border-border bg-surface px-3 py-2 text-[13px] shadow-pop">
      <p className="font-semibold text-ink">{String((p.payload as { label?: string } | undefined)?.label ?? "")}</p>
      <p className="text-text">
        <strong>{p.value}</strong> requests
      </p>
    </div>
  );
}

export function DistributionChart({ filters, rangeText }: { filters: ReportFilters; rangeText?: string }) {
  const [by, setBy] = useState<"priority" | "category">("priority");
  const q = useDistribution(by, filters);
  const total = q.data?.reduce((a, d) => a + d.count, 0) ?? 0;
  return (
    <Panel
      title="Requests by"
      actions={
        <div role="group" aria-label="Group requests by" className="inline-flex rounded-md border border-border-strong p-0.5">
          {(["priority", "category"] as const).map((v) => (
            <button
              key={v}
              type="button"
              aria-pressed={by === v}
              onClick={() => setBy(v)}
              className={`h-8 rounded-sm px-3 text-[13px] font-semibold capitalize ${by === v ? "bg-primary text-white" : "text-text hover:bg-canvas-2"}`}
            >
              {v}
            </button>
          ))}
        </div>
      }
    >
      {q.error ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : q.isLoading || !q.data ? (
        <Skeleton className="h-48 w-full" />
      ) : q.data.length === 0 ? (
        <EmptyState title="No requests in this range" />
      ) : (
        <figure aria-label={`Requests by ${by}`}>
          <p className="mb-2 text-[13px] text-muted">
            Requests by {by}
            {rangeText ? ` (${rangeText})` : ""}. Total: <strong className="text-ink">{total}</strong> requests.
          </p>
          <div aria-hidden style={{ height: Math.max(160, q.data.length * 38 + 30) }} className="w-full">
            <ResponsiveContainer width="100%" height="100%" initialDimension={{ width: 480, height: 200 }}>
              <BarChart data={q.data} layout="vertical" margin={{ top: 0, right: 24, bottom: 0, left: 8 }}>
                <CartesianGrid stroke="var(--color-border)" horizontal={false} />
                <XAxis type="number" allowDecimals={false} tick={{ fontSize: 12, fill: "var(--color-muted)" }} />
                <YAxis type="category" dataKey="label" width={110} tick={{ fontSize: 12, fill: "var(--color-text)" }} />
                <RTooltip cursor={{ fill: "var(--color-canvas-2)" }} content={(p: TipProps) => <DistTooltip {...p} />} />
                <Bar dataKey="count" name="Requests" fill="var(--color-primary)" radius={[0, 6, 6, 0]} label={{ position: "right", fontSize: 12, fill: "var(--color-ink)" }} />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <table className="sr-only">
            <caption>Requests by {by}</caption>
            <thead>
              <tr>
                <th scope="col">{by}</th>
                <th scope="col">Requests</th>
              </tr>
            </thead>
            <tbody>
              {q.data.map((d) => (
                <tr key={d.key}>
                  <th scope="row">{d.label}</th>
                  <td>{d.count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </figure>
      )}
    </Panel>
  );
}

/* ---------------- summary cards ---------------- */

export function UtilizationCard({ summary, loading, showLink }: { summary?: ReportSummary; loading?: boolean; showLink?: boolean }) {
  const u = summary?.technician_utilization;
  const exceeded = u?.percent != null && u.percent > 100;
  return (
    <Panel title="Technician utilization">
      {loading || !u ? (
        <Skeleton className="h-20 w-full" />
      ) : (
        <div className="flex flex-col gap-3">
          <p className="flex flex-wrap items-baseline gap-2">
            <span className="font-heading text-[32px] font-extrabold leading-none text-ink">{u.percent_capped == null ? "n/a" : `${u.percent_capped}%`}</span>
            <span className="text-sm text-muted">
              {u.planned_minutes} planned of {u.available_minutes} available minutes
            </span>
          </p>
          {u.percent_capped != null && (
            <div className="h-2 overflow-hidden rounded-pill bg-canvas-2" role="progressbar" aria-label="Utilization (capped at 100%)" aria-valuemin={0} aria-valuemax={100} aria-valuenow={u.percent_capped}>
              <div className="h-full bg-primary" style={{ width: `${Math.min(100, u.percent_capped)}%` }} />
            </div>
          )}
          {exceeded && <p className="text-[13px] font-semibold text-warning-dark">Raw utilization is {u.percent}%: work is planned outside availability. The figure above is capped at 100%.</p>}
          {u.percent == null && <p className="text-[13px] text-muted">No technician availability in this range, so utilization cannot be computed.</p>}
          <details className="text-[13px] text-muted">
            <summary className="flex cursor-pointer items-center gap-1.5 font-semibold text-text">
              <Info className="size-4" aria-hidden /> How utilization is calculated
            </summary>
            <p className="mt-2">{u.explanation}</p>
          </details>
          {showLink && (
            <Link href="/admin/reports" className="text-sm font-semibold text-primary hover:text-primary-dark">
              Per-technician breakdown
            </Link>
          )}
        </div>
      )}
    </Panel>
  );
}

export function EstimatesCard({ summary, loading }: { summary?: ReportSummary; loading?: boolean }) {
  return (
    <Panel title="Estimates and materials">
      {loading || !summary ? (
        <Skeleton className="h-20 w-full" />
      ) : (
        <div className="flex flex-col gap-3">
          <Badge tone="warning" icon={Wallet}>
            Estimates, not collected revenue
          </Badge>
          <dl className="grid grid-cols-2 gap-4">
            <div>
              <dt className="text-[13px] text-muted">Approved estimates</dt>
              <dd className="font-heading text-xl font-extrabold text-ink">
                <Money minor={summary.approved_estimates_total_minor} currency={summary.currency} />
              </dd>
            </div>
            <div>
              <dt className="text-[13px] text-muted">Material costs</dt>
              <dd className="font-heading text-xl font-extrabold text-ink">
                <Money minor={summary.material_costs_total_minor} currency={summary.currency} />
              </dd>
            </div>
          </dl>
          <p className="text-[12px] text-muted">Totals for the selected range: {summary.approved_estimates_label}.</p>
        </div>
      )}
    </Panel>
  );
}

export function StatusCounts({ summary, loading }: { summary?: ReportSummary; loading?: boolean }) {
  return (
    <Panel title="Requests by status">
      {loading || !summary ? (
        <Skeleton className="h-20 w-full" />
      ) : (
        <ul className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          {REQUEST_STATUSES.map((s) => {
            const m = STATUS_META[s];
            const Icon = m.icon;
            return (
              <li key={s} className="flex items-center justify-between gap-2 rounded-md bg-canvas px-3 py-2 text-sm">
                <span className="flex items-center gap-1.5 text-text">
                  <Icon className="size-4" aria-hidden />
                  {m.label}
                </span>
                <strong className="tabular-nums text-ink">{summary.counts_by_status[s] ?? 0}</strong>
              </li>
            );
          })}
        </ul>
      )}
    </Panel>
  );
}
