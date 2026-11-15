"use client";

import { AlertTriangle, ChevronLeft, ChevronRight, Flag } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Button, EmptyState, ErrorState, FormField, Input, LoadingState, PageHeader, Select, STATUS_META } from "@/components/ui";
import type { Page, Schemas } from "@/lib/api/types";
import { formatDateTime } from "@/lib/format";
import { useApiQuery } from "@/lib/query/hooks";
import { qk } from "@/lib/query/keys";
import { useAuth } from "@/lib/auth";
import { useNow } from "@/lib/use-now";
import { addDays, dayMonthLabel, dayStartIso, localDate, weekStart, weekdayShort } from "../lib/tz";
import { blockPosition, hasCoverageOn, visibleRange, weekDates } from "./layout";

type Schedule = Schemas["ScheduleOut"];
type Tech = Schemas["ScheduleTechnician"];
type Block = Schemas["ScheduleAssignment"];

const HATCH = "repeating-linear-gradient(45deg, var(--color-border-strong) 0 4px, transparent 4px 9px)";
const ROW_LABEL = "sticky left-0 z-20 flex w-40 shrink-0 flex-col justify-center border-r border-border bg-surface px-3";

/** Assign each block to a lane so overlapping blocks (conflicts) stack instead of hiding each other. */
function lanes(blocks: Block[]): { block: Block; lane: number }[] {
  const sorted = [...blocks].sort((a, b) => a.start_at.localeCompare(b.start_at));
  const ends: string[] = [];
  return sorted.map((block) => {
    let lane = ends.findIndex((e) => e <= block.start_at);
    if (lane === -1) lane = ends.length;
    ends[lane] = block.end_at;
    return { block, lane };
  });
}

function BlockBody({ b, tz }: { b: Block; tz: string }) {
  const s = STATUS_META[b.request_status];
  const Icon = s.icon;
  return (
    <>
      <span className="flex items-center gap-1 font-semibold">
        {b.conflict && <AlertTriangle className="size-3.5 shrink-0" aria-hidden />}
        {b.display_id}
        {b.priority === "HIGH" && <Flag className="size-3 shrink-0" aria-label="High priority" />}
      </span>
      <span className="truncate">{b.title}</span>
      <span className="flex items-center gap-1 text-[11px]">
        <Icon className="size-3 shrink-0" aria-hidden />
        {s.label} · {formatDateTime(b.start_at, tz, "time")}-{formatDateTime(b.end_at, tz, "time")}
      </span>
      {b.conflict && <span className="text-[11px] font-semibold">Conflict{b.conflict_reasons.length ? `: ${b.conflict_reasons.join(", ").replaceAll("_", " ")}` : ""}</span>}
    </>
  );
}

function blockLabel(b: Block, tz: string) {
  return `${b.display_id} ${b.title}, ${STATUS_META[b.request_status].label}, ${formatDateTime(b.start_at, tz, "short")} to ${formatDateTime(b.end_at, tz, "time")}${b.conflict ? ", scheduling conflict" : ""}`;
}

function blockTone(b: Block) {
  if (b.conflict) return "border-danger bg-danger-tint text-danger-dark";
  if (b.request_status === "BLOCKED") return "border-warning bg-warning-tint text-warning-dark";
  if (b.request_status === "IN_PROGRESS") return "border-primary bg-primary-tint text-primary-dark";
  return "border-info/50 bg-info-tint text-ink";
}

function DayBoard({ data, date, tz }: { data: Schedule; date: string; tz: string }) {
  const all = data.technicians.flatMap((t) => [...t.availability, ...t.assignments]);
  const { start, end } = visibleRange(all, tz, date);
  const hours = Array.from({ length: (end - start) / 60 }, (_, i) => start / 60 + i);
  const span = end - start;
  return (
    <div role="region" aria-label="Day schedule" tabIndex={0} className="overflow-x-auto rounded-xl border border-border bg-surface shadow-panel">
      <div style={{ minWidth: 160 + hours.length * 72 }}>
        <div className="flex border-b border-border bg-canvas text-xs text-muted">
          <div className={`${ROW_LABEL} h-9 bg-canvas font-semibold`}>Technician</div>
          <div className="relative h-9 flex-1" aria-hidden>
            {hours.map((h, i) => (
              <span key={h} className="absolute top-2.5 -translate-x-1/2 tabular-nums" style={{ left: `${(i / hours.length) * 100}%`, marginLeft: i === 0 ? 14 : 0 }}>
                {String(h).padStart(2, "0")}:00
              </span>
            ))}
          </div>
        </div>
        {data.technicians.map((t) => (
          <DayRow key={t.membership_id} t={t} date={date} tz={tz} start={start} span={span} hours={hours.length} />
        ))}
      </div>
    </div>
  );
}

function DayRow({ t, date, tz, start, span, hours }: { t: Tech; date: string; tz: string; start: number; span: number; hours: number }) {
  const laid = lanes(t.assignments.filter((a) => blockPosition(a.start_at, a.end_at, tz, date, start, start + span)));
  const laneCount = Math.max(1, ...laid.map((l) => l.lane + 1));
  const height = laneCount * 52 + 8;
  return (
    <div className="flex border-b border-border last:border-0">
      <div className={ROW_LABEL}>
        <span className="truncate text-sm font-semibold text-ink">{t.name.replace(/ \(.*\)$/, "")}</span>
        {!t.is_active && <span className="text-xs text-muted">Inactive</span>}
      </div>
      <div className="relative flex-1 bg-canvas-2" style={{ height }} role="group" aria-label={`${t.name} on ${dayMonthLabel(date)}`}>
        {t.availability.map((a, i) => {
          const p = blockPosition(a.start_at, a.end_at, tz, date, start, start + span);
          return p && <div key={i} data-kind="availability" className="absolute inset-y-0 bg-surface" style={{ left: `${p.left}%`, width: `${p.width}%` }} />;
        })}
        {Array.from({ length: hours }, (_, i) => (
          <div key={i} aria-hidden className="absolute inset-y-0 border-l border-border/70" style={{ left: `${(i / hours) * 100}%` }} />
        ))}
        {t.time_off.map((o) => {
          const p = blockPosition(o.start_at, o.end_at, tz, date, start, start + span);
          return (
            p && (
              <div key={o.id} data-kind="time-off" title={`Time off${o.reason ? `: ${o.reason}` : ""}`} className="absolute inset-y-0 flex items-center justify-center overflow-hidden text-[11px] font-semibold text-muted" style={{ left: `${p.left}%`, width: `${p.width}%`, backgroundImage: HATCH }}>
                <span className="rounded-sm bg-surface/90 px-1">Time off</span>
              </div>
            )
          );
        })}
        {laid.map(({ block, lane }) => {
          const p = blockPosition(block.start_at, block.end_at, tz, date, start, start + span)!;
          return (
            <Link
              key={block.assignment_id}
              href={`/requests/${block.request_id}`}
              aria-label={blockLabel(block, tz)}
              data-testid={`block-${block.display_id}`}
              className={`absolute flex min-w-0 flex-col overflow-hidden rounded-md border px-1.5 py-1 text-xs leading-tight shadow-sm hover:ring-2 hover:ring-primary ${blockTone(block)}`}
              style={{ left: `${p.left}%`, width: `${p.width}%`, top: 4 + lane * 52, height: 48 }}
            >
              <BlockBody b={block} tz={tz} />
            </Link>
          );
        })}
      </div>
    </div>
  );
}

/** One template for the header and EVERY technician row, so day columns line up regardless of stacked blocks. */
export const WEEK_GRID = "160px repeat(7, minmax(140px, 1fr))";

function WeekBoard({ data, monday, tz }: { data: Schedule; monday: string; tz: string }) {
  const days = weekDates(monday);
  return (
    <div role="region" aria-label="Week schedule" tabIndex={0} className="overflow-x-auto rounded-xl border border-border bg-surface shadow-panel">
      <div style={{ minWidth: 160 + 7 * 150 }}>
        <div data-week-row="header" className="grid border-b border-border bg-canvas text-xs font-semibold text-muted" style={{ gridTemplateColumns: WEEK_GRID }}>
          <div className={`${ROW_LABEL} h-9 bg-canvas`}>Technician</div>
          {days.map((d) => (
            <div key={d} className="flex h-9 min-w-0 items-center border-l border-border px-2">
              {weekdayShort(d)} {dayMonthLabel(d)}
            </div>
          ))}
        </div>
        {data.technicians.map((t) => (
          <div key={t.membership_id} data-week-row="tech" className="grid border-b border-border last:border-0" style={{ gridTemplateColumns: WEEK_GRID }}>
            <div className={ROW_LABEL}>
              <span className="truncate text-sm font-semibold text-ink">{t.name.replace(/ \(.*\)$/, "")}</span>
            </div>
            {days.map((d) => {
              const here = lanes(t.assignments.filter((a) => blockPosition(a.start_at, a.end_at, tz, d, 0, 1440)));
              const off = t.time_off.some((o) => blockPosition(o.start_at, o.end_at, tz, d, 0, 1440));
              const free = hasCoverageOn(t.availability, tz, d);
              return (
                <div
                  key={d}
                  data-day={d}
                  role="group"
                  aria-label={`${t.name} on ${dayMonthLabel(d)}${off ? ", time off" : free ? "" : ", not available"}`}
                  className={`flex min-h-20 min-w-0 flex-col gap-1 border-l border-border p-1 ${free && !off ? "bg-surface" : "bg-canvas-2"}`}
                  style={off ? { backgroundImage: HATCH } : undefined}
                >
                  {off && <span className="w-fit rounded-sm bg-surface/90 px-1 text-[11px] font-semibold text-muted">Time off</span>}
                  {!off && !free && <span className="text-[11px] text-muted">Not available</span>}
                  {here.map(({ block }) => (
                    <Link
                      key={block.assignment_id}
                      href={`/requests/${block.request_id}`}
                      aria-label={blockLabel(block, tz)}
                      data-testid={`block-${block.display_id}`}
                      className={`flex min-w-0 flex-col overflow-hidden rounded-md border px-1.5 py-1 text-xs leading-tight hover:ring-2 hover:ring-primary ${blockTone(block)}`}
                    >
                      <BlockBody b={block} tz={tz} />
                    </Link>
                  ))}
                </div>
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}

export function SchedulePage() {
  const router = useRouter();
  const pathname = usePathname();
  const sp = useSearchParams();
  const { timezone: tz } = useAuth();
  const now = useNow();
  const view = sp.get("view") === "week" ? "week" : "day";
  const today = now > 0 ? localDate(now, tz) : "";
  const picked = sp.get("date");
  const date = picked && /^\d{4}-\d{2}-\d{2}$/.test(picked) ? picked : today;
  const technician = sp.get("technician_id") ?? "";
  const anchor = date ? (view === "week" ? weekStart(date) : date) : "";
  const to = anchor ? addDays(anchor, view === "week" ? 7 : 1) : "";
  const params = { from: anchor ? dayStartIso(anchor, tz) : undefined, to: to ? dayStartIso(to, tz) : undefined, technician_id: technician || undefined };

  const techs = useApiQuery<Page<Schemas["TechnicianOut"]>>({ queryKey: (o) => qk.technicians.list(o, { page_size: 100 }), path: "/technicians", query: { page_size: 100 }, staleTime: 60_000 });
  const q = useApiQuery<Schedule>({ queryKey: (o) => qk.schedule.range(o, params), path: "/schedule", query: params, enabled: Boolean(anchor) });

  function go(next: { view?: string; date?: string; technician_id?: string }) {
    const n = new URLSearchParams();
    const v = next.view ?? view;
    const d = next.date ?? date;
    const t = next.technician_id ?? technician;
    if (v === "week") n.set("view", "week");
    if (d && d !== today) n.set("date", d);
    if (t) n.set("technician_id", t);
    const qs = n.toString();
    router.replace(qs ? `${pathname}?${qs}` : pathname);
  }
  const step = view === "week" ? 7 : 1;
  const heading = !anchor ? "" : view === "week" ? `${dayMonthLabel(anchor)} - ${dayMonthLabel(addDays(anchor, 6))}` : `${weekdayShort(anchor)} ${dayMonthLabel(anchor)}`;

  return (
    <>
      <PageHeader title="Schedule board" description={`Technicians, appointments, availability and time off. Times in ${tz}.`} />
      <div className="mb-4 flex flex-wrap items-end gap-3 rounded-xl border border-border bg-surface p-3" role="toolbar" aria-label="Schedule controls">
        <div role="group" aria-label="View" className="inline-flex rounded-md border border-border-strong p-0.5">
          {(["day", "week"] as const).map((v) => (
            <button key={v} type="button" aria-pressed={view === v} onClick={() => go({ view: v })} className={`rounded-sm px-3 py-1.5 text-sm font-semibold ${view === v ? "bg-primary text-white" : "text-text hover:bg-canvas-2"}`}>
              {v === "day" ? "Day" : "Week"}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-1.5">
          <Button variant="secondary" aria-label={view === "week" ? "Previous week" : "Previous day"} onClick={() => date && go({ date: addDays(date, -step) })}>
            <ChevronLeft className="size-4" aria-hidden />
          </Button>
          <Button variant="secondary" onClick={() => go({ date: today })}>
            Today
          </Button>
          <Button variant="secondary" aria-label={view === "week" ? "Next week" : "Next day"} onClick={() => date && go({ date: addDays(date, step) })}>
            <ChevronRight className="size-4" aria-hidden />
          </Button>
        </div>
        <FormField label="Go to date" className="w-44">
          <Input type="date" value={date} onChange={(e) => e.target.value && go({ date: e.target.value })} />
        </FormField>
        <FormField label="Technician" className="w-56">
          <Select value={technician} onChange={(e) => go({ technician_id: e.target.value })}>
            <option value="">All technicians</option>
            {techs.data?.items.map((t) => (
              <option key={t.membership_id} value={t.membership_id}>
                {t.full_name.replace(/ \(.*\)$/, "")}
              </option>
            ))}
          </Select>
        </FormField>
        <p className="ml-auto text-base font-semibold text-ink" aria-live="polite">
          {heading}
        </p>
      </div>

      <ul className="mb-3 flex flex-wrap gap-x-5 gap-y-1 text-xs text-muted" aria-label="Legend">
        <li className="flex items-center gap-1.5"><span className="size-3 rounded-sm border border-border bg-surface" aria-hidden /> Available</li>
        <li className="flex items-center gap-1.5"><span className="size-3 rounded-sm bg-canvas-2" aria-hidden /> Not available</li>
        <li className="flex items-center gap-1.5"><span className="size-3 rounded-sm" style={{ backgroundImage: HATCH }} aria-hidden /> Time off</li>
        <li className="flex items-center gap-1.5"><AlertTriangle className="size-3.5 text-danger-dark" aria-hidden /> Scheduling conflict</li>
      </ul>

      {q.isLoading || !anchor ? (
        <LoadingState label="Loading schedule" />
      ) : q.error ? (
        <ErrorState error={q.error} onRetry={() => void q.refetch()} />
      ) : q.data && q.data.technicians.length === 0 ? (
        <EmptyState title="No technicians to show" description="Add technicians in Admin, or clear the technician filter." />
      ) : q.data ? (
        view === "day" ? <DayBoard data={q.data} date={anchor} tz={tz} /> : <WeekBoard data={q.data} monday={anchor} tz={tz} />
      ) : null}
    </>
  );
}
