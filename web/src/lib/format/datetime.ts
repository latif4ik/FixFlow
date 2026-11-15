export type DateStyle = "datetime" | "date" | "time" | "short";

function toDate(value: string | number | Date): Date {
  return value instanceof Date ? value : new Date(value);
}

const cache = new Map<string, Intl.DateTimeFormat>();
function fmt(tz: string, opts: Intl.DateTimeFormatOptions, key: string): Intl.DateTimeFormat {
  const k = `${tz}|${key}`;
  let f = cache.get(k);
  if (!f) {
    f = new Intl.DateTimeFormat("en-GB", { timeZone: tz, ...opts });
    cache.set(k, f);
  }
  return f;
}

/** Format an instant in the given IANA timezone (use the ORG timezone, never the browser's). */
export function formatDateTime(value: string | number | Date, tz: string, style: DateStyle = "datetime"): string {
  const d = toDate(value);
  if (Number.isNaN(d.getTime())) return "";
  const time = () => fmt(tz, { hour: "2-digit", minute: "2-digit", hourCycle: "h23" }, "time").format(d);
  // Date and time are formatted separately and joined with ", " so output does not depend on the ICU version
  // ("15 Nov 2026 at 09:02" vs "15 Nov 2026, 09:02").
  switch (style) {
    case "time":
      return time();
    case "date":
      return fmt(tz, { day: "numeric", month: "short", year: "numeric" }, "date").format(d);
    case "short":
      return `${fmt(tz, { day: "numeric", month: "short" }, "short-date").format(d)}, ${time()}`;
    default:
      return `${fmt(tz, { day: "numeric", month: "short", year: "numeric" }, "date").format(d)}, ${time()}`;
  }
}

/** "50 min", "2 h 5 min", "3 d". Input in minutes (>= 0). */
export function formatDuration(minutes: number): string {
  const m = Math.max(0, Math.round(minutes));
  if (m < 60) return `${m} min`;
  if (m < 24 * 60) {
    const h = Math.floor(m / 60);
    const r = m % 60;
    return r ? `${h} h ${r} min` : `${h} h`;
  }
  const d = Math.floor(m / (24 * 60));
  const h = Math.round((m % (24 * 60)) / 60);
  return h ? `${d} d ${h} h` : `${d} d`;
}

/** "in 50 min" / "12 min ago" relative to `now`. */
export function formatRelative(value: string | number | Date, now: Date = new Date()): string {
  const diffMin = Math.round((toDate(value).getTime() - now.getTime()) / 60000);
  if (Math.abs(diffMin) < 1) return "just now";
  const text = formatDuration(Math.abs(diffMin));
  return diffMin > 0 ? `in ${text}` : `${text} ago`;
}
