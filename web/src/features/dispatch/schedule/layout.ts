import { addDays, localDate, localMinutes } from "../lib/tz";

export interface Interval {
  start_at: string;
  end_at: string;
}

/**
 * Visible hour range (minutes since local midnight) for the day view: the span of availability and assignments
 * seen in the data, padded by one hour, clamped to 0-24 h. Defaults to 08:00-19:00 when there is no data.
 */
export function visibleRange(intervals: Interval[], tz: string, date: string): { start: number; end: number } {
  let lo = Infinity;
  let hi = -Infinity;
  for (const i of intervals) {
    const s = localDate(i.start_at, tz) === date ? localMinutes(i.start_at, tz) : localDate(i.start_at, tz) < date ? 0 : 24 * 60;
    const eDate = localDate(new Date(new Date(i.end_at).getTime() - 1), tz);
    const e = eDate === date ? localMinutes(new Date(new Date(i.end_at).getTime() - 1), tz) + 1 : eDate > date ? 24 * 60 : 0;
    if (e <= s) continue;
    lo = Math.min(lo, s);
    hi = Math.max(hi, e);
  }
  if (!Number.isFinite(lo)) return { start: 8 * 60, end: 19 * 60 };
  const start = Math.max(0, Math.floor(lo / 60) * 60 - 60);
  const end = Math.min(24 * 60, Math.ceil(hi / 60) * 60 + 60);
  return { start, end };
}

/** Left/width in percent of a block inside a day column showing [rangeStart, rangeEnd) minutes. null = not on this day. */
export function blockPosition(startIso: string, endIso: string, tz: string, date: string, rangeStart: number, rangeEnd: number): { left: number; width: number } | null {
  const span = rangeEnd - rangeStart;
  const sDate = localDate(startIso, tz);
  const lastMs = new Date(endIso).getTime() - 1;
  const eDate = localDate(lastMs, tz);
  if (sDate > date || eDate < date) return null;
  const s = sDate === date ? localMinutes(startIso, tz) : 0;
  const e = eDate === date ? localMinutes(lastMs, tz) + 1 : 24 * 60;
  const from = Math.max(s, rangeStart);
  const to = Math.min(e, rangeEnd);
  if (to <= from) return null;
  return { left: ((from - rangeStart) / span) * 100, width: ((to - from) / span) * 100 };
}

export function weekDates(monday: string): string[] {
  return Array.from({ length: 7 }, (_, i) => addDays(monday, i));
}

/** Does any interval cover the whole local day partly? Used to shade weekdays with no availability. */
export function hasCoverageOn(intervals: Interval[], tz: string, date: string): boolean {
  return intervals.some((i) => blockPosition(i.start_at, i.end_at, tz, date, 0, 24 * 60) !== null);
}
