"use client";

import Link from "next/link";
import { EmptyState, ErrorState, Panel, Skeleton, STATUS_META } from "@/components/ui";
import type { Schemas } from "@/lib/api";
import { useOrgTimezone } from "@/lib/auth";
import { formatDateTime } from "@/lib/format";
import { qk, useApiQuery } from "@/lib/query";
import { useNow } from "@/lib/use-now";
import { addDaysYmd, ymdInTz, zonedInstant } from "./tz";

const DAY_START = 8;
const DAY_END = 18;

export type Schedule = Schemas["ScheduleOut"];

/** Schedule for "today" in the organization timezone. */
export function useTodaySchedule() {
  const tz = useOrgTimezone();
  const now = useNow();
  const today = now ? ymdInTz(now, tz) : "";
  const from = today ? new Date(zonedInstant(today, 0, 0, tz)).toISOString() : "";
  const to = today ? new Date(zonedInstant(addDaysYmd(today, 1), 0, 0, tz)).toISOString() : "";
  const q = useApiQuery<Schedule>({ queryKey: (o) => qk.schedule.range(o, { from, to }), path: "/schedule", query: { from, to }, enabled: Boolean(today) });
  return { ...q, today, now };
}

export function DayTimeline({ schedule, loading, error, onRetry, today, now }: { schedule?: Schedule; loading?: boolean; error?: { message: string } | null; onRetry?: () => void; today: string; now: number }) {
  const tz = useOrgTimezone();
  const start = today ? zonedInstant(today, DAY_START, 0, tz) : 0;
  const end = today ? zonedInstant(today, DAY_END, 0, tz) : 1;
  const pct = (t: number) => Math.min(100, Math.max(0, ((t - start) / (end - start)) * 100));
  const nowPct = now >= start && now <= end ? pct(now) : null;
  const hours = Array.from({ length: DAY_END - DAY_START + 1 }, (_, i) => DAY_START + i);
  const techs = schedule?.technicians.filter((t) => t.is_active) ?? [];

  return (
    <Panel title="Today's appointments" actions={<span className="text-[13px] text-muted">{DAY_START}:00 to {DAY_END}:00, {tz} time</span>}>
      {error ? (
        <ErrorState error={error} onRetry={onRetry} />
      ) : loading || !schedule ? (
        <Skeleton className="h-40 w-full" />
      ) : techs.length === 0 ? (
        <EmptyState title="No active technicians" description="Add technicians in Admin to see their day here." />
      ) : (
        <div className="overflow-x-auto">
          <div className="min-w-[720px]">
            <div className="flex">
              <div className="w-36 shrink-0" />
              <div className="relative h-6 flex-1" aria-hidden>
                {hours.map((h) => (
                  <span key={h} className="absolute -translate-x-1/2 text-[12px] text-muted" style={{ left: `${((h - DAY_START) / (DAY_END - DAY_START)) * 100}%` }}>
                    {String(h).padStart(2, "0")}:00
                  </span>
                ))}
              </div>
            </div>
            <ul className="flex flex-col">
              {techs.map((t) => {
                const items = t.assignments.filter((a) => new Date(a.end_at).getTime() > start && new Date(a.start_at).getTime() < end);
                return (
                  <li key={t.membership_id} className="flex items-stretch border-t border-border">
                    <div className="flex w-36 shrink-0 items-center pr-3 text-sm font-semibold text-ink">
                      <span className="truncate" title={t.name}>
                        {t.name.replace(/\s*\(.*\)$/, "")}
                      </span>
                    </div>
                    <div className="relative h-14 flex-1" role="group" aria-label={`${t.name}: ${t.assignments.length} appointments today`}>
                      {hours.map((h) => (
                        <span key={h} aria-hidden className="absolute inset-y-0 w-px bg-border" style={{ left: `${((h - DAY_START) / (DAY_END - DAY_START)) * 100}%` }} />
                      ))}
                      {items.map((a) => {
                        const left = pct(new Date(a.start_at).getTime());
                        const right = pct(new Date(a.end_at).getTime());
                        const m = STATUS_META[a.request_status];
                        const Icon = m.icon;
                        return (
                          <Link
                            key={a.assignment_id}
                            href={`/requests/${a.request_id}`}
                            title={`${a.display_id} ${a.title}, ${formatDateTime(a.start_at, tz, "time")} to ${formatDateTime(a.end_at, tz, "time")}, ${m.label}`}
                            className="absolute inset-y-1.5 flex min-w-8 flex-col justify-center overflow-hidden rounded-md border border-primary/40 bg-primary-tint px-2 text-[12px] leading-tight text-primary-dark hover:bg-primary-tint-2"
                            style={{ left: `${left}%`, width: `${Math.max(right - left, 2)}%` }}
                          >
                            <span className="truncate font-semibold">{a.display_id}</span>
                            <span className="flex items-center gap-1 truncate">
                              <Icon className="size-3 shrink-0" aria-hidden />
                              {m.label}
                            </span>
                          </Link>
                        );
                      })}
                      {nowPct !== null && <span aria-hidden className="absolute inset-y-0 w-0.5 bg-danger" style={{ left: `${nowPct}%` }} />}
                    </div>
                  </li>
                );
              })}
            </ul>
            {nowPct !== null && (
              <p className="mt-2 flex items-center gap-2 text-[12px] text-muted">
                <span aria-hidden className="inline-block h-3 w-0.5 bg-danger" />
                Now, {formatDateTime(now, tz, "time")}
              </p>
            )}
          </div>
        </div>
      )}
    </Panel>
  );
}
