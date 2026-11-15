import { describe, expect, it } from "vitest";
import { formatDateTime, formatDuration, formatRelative } from "./datetime";
import { formatMoney } from "./money";
import { initials } from "./index";

describe("formatMoney", () => {
  it("formats tyiyn with a space thousands separator and 2 decimals", () => {
    expect(formatMoney(494000)).toBe("4 940.00 KGS");
    expect(formatMoney(120000)).toBe("1 200.00 KGS");
    expect(formatMoney(5)).toBe("0.05 KGS");
    expect(formatMoney(0)).toBe("0.00 KGS");
    expect(formatMoney(123456789)).toBe("1 234 567.89 KGS");
  });
  it("handles negatives and other currencies", () => {
    expect(formatMoney(-150050, "USD")).toBe("-1 500.50 USD");
  });
});

describe("formatDateTime", () => {
  it("renders an instant in the given timezone, not the machine's", () => {
    const iso = "2026-11-15T03:02:00Z";
    expect(formatDateTime(iso, "Asia/Bishkek")).toBe("15 Nov 2026, 09:02");
    expect(formatDateTime(iso, "UTC")).toBe("15 Nov 2026, 03:02");
    expect(formatDateTime(iso, "America/New_York", "time")).toBe("22:02");
  });
  it("crosses midnight correctly per timezone", () => {
    expect(formatDateTime("2026-11-15T20:30:00Z", "Asia/Bishkek", "date")).toBe("16 Nov 2026");
    expect(formatDateTime("2026-11-15T20:30:00Z", "UTC", "date")).toBe("15 Nov 2026");
  });
  it("formats durations and relative times", () => {
    expect(formatDuration(50)).toBe("50 min");
    expect(formatDuration(125)).toBe("2 h 5 min");
    const now = new Date("2026-11-15T10:00:00Z");
    expect(formatRelative("2026-11-15T10:50:00Z", now)).toBe("in 50 min");
    expect(formatRelative("2026-11-15T09:48:00Z", now)).toBe("12 min ago");
  });
  it("builds initials", () => {
    expect(initials("Aibek Dzhumabaev")).toBe("AD");
    expect(initials("Dispatcher (Northwind Facilities)")).toBe("D");
  });
});
