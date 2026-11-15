/** Timezone helpers: everything is computed in the ORGANIZATION timezone, never the browser's. */

const parts = (ms: number, tz: string) => {
  const f = new Intl.DateTimeFormat("en-CA", { timeZone: tz, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23" });
  const o: Record<string, number> = {};
  for (const p of f.formatToParts(new Date(ms))) if (p.type !== "literal") o[p.type] = Number(p.value);
  return o as { year: number; month: number; day: number; hour: number; minute: number; second: number };
};

/** "YYYY-MM-DD" of an instant in the given timezone. */
export function ymdInTz(ms: number, tz: string): string {
  const p = parts(ms, tz);
  return `${p.year}-${String(p.month).padStart(2, "0")}-${String(p.day).padStart(2, "0")}`;
}

/** The instant (ms) at which wall-clock `ymd hh:mm` happens in `tz`. */
export function zonedInstant(ymd: string, hh: number, mm: number, tz: string): number {
  const [y, m, d] = ymd.split("-").map(Number) as [number, number, number];
  const guess = Date.UTC(y, m - 1, d, hh, mm);
  const off = (at: number) => {
    const p = parts(at, tz);
    return Date.UTC(p.year, p.month - 1, p.day, p.hour, p.minute, p.second) - at;
  };
  const first = guess - off(guess);
  return guess - off(first);
}

/** Adds days to a "YYYY-MM-DD" (calendar arithmetic, tz independent). */
export function addDaysYmd(ymd: string, days: number): string {
  const [y, m, d] = ymd.split("-").map(Number) as [number, number, number];
  return new Date(Date.UTC(y, m - 1, d + days)).toISOString().slice(0, 10);
}

export function formatDayLong(ms: number, tz: string): string {
  return new Intl.DateTimeFormat("en-GB", { timeZone: tz, weekday: "long", day: "numeric", month: "long" }).format(new Date(ms));
}

export function formatYmd(ymd: string): string {
  const [y, m, d] = ymd.split("-").map(Number) as [number, number, number];
  return new Intl.DateTimeFormat("en-GB", { timeZone: "UTC", day: "numeric", month: "short" }).format(new Date(Date.UTC(y, m - 1, d)));
}
