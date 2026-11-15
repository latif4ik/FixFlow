/** Helpers to interpret wall-clock input in the ORG timezone (never the browser's) and convert to UTC ISO. */

function offsetMinutes(utcMs: number, tz: string): number {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: tz,
    hourCycle: "h23",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).formatToParts(new Date(utcMs));
  const g = (t: string) => Number(parts.find((p) => p.type === t)?.value ?? 0);
  const asUtc = Date.UTC(g("year"), g("month") - 1, g("day"), g("hour"), g("minute"), g("second"));
  return Math.round((asUtc - utcMs) / 60000);
}

/** "2026-11-20" + "09:30" in `tz` -> UTC ISO string. Returns null for invalid input. */
export function zonedToUtcIso(date: string, time: string, tz: string): string | null {
  const d = /^(\d{4})-(\d{2})-(\d{2})$/.exec(date);
  const t = /^(\d{2}):(\d{2})$/.exec(time);
  if (!d || !t) return null;
  const wall = Date.UTC(Number(d[1]), Number(d[2]) - 1, Number(d[3]), Number(t[1]), Number(t[2]));
  if (Number.isNaN(wall)) return null;
  let guess = wall - offsetMinutes(wall, tz) * 60000;
  guess = wall - offsetMinutes(guess, tz) * 60000;
  return new Date(guess).toISOString();
}

/** UTC ISO -> { date: "YYYY-MM-DD", time: "HH:mm" } in `tz`. */
export function utcIsoToZoned(iso: string, tz: string): { date: string; time: string } {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: tz,
    hourCycle: "h23",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).formatToParts(new Date(iso));
  const g = (t: string) => parts.find((p) => p.type === t)?.value ?? "";
  return { date: `${g("year")}-${g("month")}-${g("day")}`, time: `${g("hour")}:${g("minute")}` };
}
