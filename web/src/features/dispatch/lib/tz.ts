/**
 * Org-timezone helpers (never the browser timezone). A "local date" is "YYYY-MM-DD" and a "local time" is "HH:MM",
 * both as seen on a wall clock in the given IANA zone.
 */
const partsCache = new Map<string, Intl.DateTimeFormat>();

function parts(tz: string): Intl.DateTimeFormat {
  let f = partsCache.get(tz);
  if (!f) {
    f = new Intl.DateTimeFormat("en-US", {
      timeZone: tz,
      hourCycle: "h23",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
    partsCache.set(tz, f);
  }
  return f;
}

function wall(ms: number, tz: string) {
  const o: Record<string, number> = {};
  for (const p of parts(tz).formatToParts(new Date(ms))) {
    if (p.type !== "literal") o[p.type] = Number(p.value);
  }
  return { y: o.year!, mo: o.month!, d: o.day!, h: o.hour! % 24, mi: o.minute!, s: o.second! };
}

/** Offset (minutes, east positive) of `tz` at the instant `ms`. */
export function tzOffsetMinutes(ms: number, tz: string): number {
  const w = wall(ms, tz);
  const asUtc = Date.UTC(w.y, w.mo - 1, w.d, w.h, w.mi, w.s);
  return Math.round((asUtc - Math.floor(ms / 1000) * 1000) / 60000);
}

/** Wall-clock date + time in `tz` -> UTC ISO string (handles DST gaps by re-resolving the offset). */
export function zonedToUtcIso(date: string, time: string, tz: string): string {
  const [y, mo, d] = date.split("-").map(Number) as [number, number, number];
  const [h, mi] = time.split(":").map(Number) as [number, number];
  const guess = Date.UTC(y, mo - 1, d, h, mi);
  const off1 = tzOffsetMinutes(guess, tz);
  let utc = guess - off1 * 60000;
  const off2 = tzOffsetMinutes(utc, tz);
  if (off2 !== off1) utc = guess - off2 * 60000;
  return new Date(utc).toISOString();
}

/** "YYYY-MM-DD" of an instant as seen in `tz`. */
export function localDate(value: string | number | Date, tz: string): string {
  const w = wall(new Date(value).getTime(), tz);
  return `${w.y}-${String(w.mo).padStart(2, "0")}-${String(w.d).padStart(2, "0")}`;
}

/** "HH:MM" of an instant as seen in `tz`. */
export function localTime(value: string | number | Date, tz: string): string {
  const w = wall(new Date(value).getTime(), tz);
  return `${String(w.h).padStart(2, "0")}:${String(w.mi).padStart(2, "0")}`;
}

/** Minutes since local midnight of an instant in `tz`. */
export function localMinutes(value: string | number | Date, tz: string): number {
  const w = wall(new Date(value).getTime(), tz);
  return w.h * 60 + w.mi;
}

export function addDays(date: string, n: number): string {
  const [y, m, d] = date.split("-").map(Number) as [number, number, number];
  const t = new Date(Date.UTC(y, m - 1, d + n));
  return `${t.getUTCFullYear()}-${String(t.getUTCMonth() + 1).padStart(2, "0")}-${String(t.getUTCDate()).padStart(2, "0")}`;
}

/** Monday of the week containing `date`. */
export function weekStart(date: string): string {
  const [y, m, d] = date.split("-").map(Number) as [number, number, number];
  const dow = new Date(Date.UTC(y, m - 1, d)).getUTCDay(); // 0 = Sunday
  return addDays(date, -((dow + 6) % 7));
}

/** UTC ISO of local midnight starting `date` in `tz`. */
export function dayStartIso(date: string, tz: string): string {
  return zonedToUtcIso(date, "00:00", tz);
}

export function weekdayShort(date: string): string {
  const [y, m, d] = date.split("-").map(Number) as [number, number, number];
  return new Intl.DateTimeFormat("en-GB", { weekday: "short", timeZone: "UTC" }).format(new Date(Date.UTC(y, m - 1, d)));
}

export function dayMonthLabel(date: string): string {
  const [y, m, d] = date.split("-").map(Number) as [number, number, number];
  return new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", timeZone: "UTC" }).format(new Date(Date.UTC(y, m - 1, d)));
}

/** Server error `details` helper: pulls a readable list of reasons from a 422 technician_ineligible. */
export function reasonMessages(details: unknown): string[] {
  const d = details as { reasons?: { message?: string }[] } | null;
  if (!d || !Array.isArray(d.reasons)) return [];
  return d.reasons.map((r) => r.message ?? "").filter(Boolean);
}
