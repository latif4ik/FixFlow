import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { renderWithProviders } from "@/test/render";
import { apiUrl, http, HttpResponse, server } from "@/test/server";
import { addDays, localDate, localMinutes, weekStart, zonedToUtcIso } from "../lib/tz";
import { blockPosition, visibleRange } from "./layout";
import { SchedulePage } from "./schedule-page";

const TZ = "Asia/Bishkek"; // UTC+6, no DST

describe("org-timezone helpers", () => {
  it("converts wall-clock time in the org zone to UTC and back", () => {
    expect(zonedToUtcIso("2026-11-16", "09:00", TZ)).toBe("2026-11-16T03:00:00.000Z");
    expect(zonedToUtcIso("2026-11-16", "00:00", TZ)).toBe("2026-11-15T18:00:00.000Z");
    expect(localDate("2026-11-15T20:00:00Z", TZ)).toBe("2026-11-16");
    expect(localMinutes("2026-11-16T03:30:00Z", TZ)).toBe(9 * 60 + 30);
    // DST zone: Europe/Berlin is +1 in winter, +2 in summer
    expect(zonedToUtcIso("2026-01-15", "09:00", "Europe/Berlin")).toBe("2026-01-15T08:00:00.000Z");
    expect(zonedToUtcIso("2026-07-15", "09:00", "Europe/Berlin")).toBe("2026-07-15T07:00:00.000Z");
  });
  it("computes weeks starting Monday", () => {
    expect(weekStart("2026-11-16")).toBe("2026-11-16"); // Monday
    expect(weekStart("2026-11-22")).toBe("2026-11-16"); // Sunday
    expect(addDays("2026-11-30", 1)).toBe("2026-12-01");
  });
});

describe("block layout", () => {
  it("positions by org-local time inside the visible range", () => {
    const p = blockPosition("2026-11-16T03:00:00Z", "2026-11-16T04:00:00Z", TZ, "2026-11-16", 8 * 60, 19 * 60)!;
    expect(p.left).toBeCloseTo((1 / 11) * 100, 5); // 09:00 local in an 08:00-19:00 range
    expect(p.width).toBeCloseTo((1 / 11) * 100, 5);
    expect(blockPosition("2026-11-16T03:00:00Z", "2026-11-16T04:00:00Z", TZ, "2026-11-17", 0, 1440)).toBeNull();
  });
  it("derives the range from availability with one hour of padding", () => {
    expect(visibleRange([{ start_at: "2026-11-16T03:00:00Z", end_at: "2026-11-16T12:00:00Z" }], TZ, "2026-11-16")).toEqual({ start: 8 * 60, end: 19 * 60 });
    expect(visibleRange([], TZ, "2026-11-16")).toEqual({ start: 8 * 60, end: 19 * 60 });
  });
});

const schedule = (conflict = false) => ({
  range: { from: "2026-11-15T18:00:00Z", to: "2026-11-16T18:00:00Z", timezone: TZ },
  technicians: [
    {
      membership_id: "t1",
      name: "Technician One (Northwind)",
      is_active: true,
      availability: [{ start_at: "2026-11-16T03:00:00Z", end_at: "2026-11-16T12:00:00Z" }],
      time_off: [],
      assignments: [
        { assignment_id: "a1", request_id: "r7", display_id: "REQ-7", title: "Replace lights", priority: "NORMAL", request_status: "SCHEDULED", assignment_status: "ACTIVE", start_at: "2026-11-16T03:00:00Z", end_at: "2026-11-16T04:00:00Z", conflict, conflict_reasons: conflict ? ["overlap"] : [] },
      ],
    },
    {
      membership_id: "t2",
      name: "Technician Two (Northwind)",
      is_active: true,
      availability: [],
      time_off: [{ id: "o1", start_at: "2026-11-15T18:00:00Z", end_at: "2026-11-16T18:00:00Z", reason: "Leave" }],
      assignments: [],
    },
  ],
});

describe("SchedulePage", () => {
  it("day view: places the block at the org-local 09:00 column and shows time off", async () => {
    let url: URL | null = null;
    server.use(
      http.get(apiUrl("/technicians"), () => HttpResponse.json({ items: [], total: 0, page: 1, page_size: 100 })),
      http.get(apiUrl("/schedule"), ({ request }) => {
        url = new URL(request.url);
        return HttpResponse.json(schedule());
      }),
    );
    renderWithProviders(<SchedulePage />, { route: "/schedule", search: { date: "2026-11-16" } });
    const block = await screen.findByTestId("block-REQ-7");
    expect(parseFloat(block.style.left)).toBeCloseTo(9.0909, 3);
    expect(parseFloat(block.style.width)).toBeCloseTo(9.0909, 3);
    expect(block).toHaveAttribute("href", "/requests/r7");
    expect(block).toHaveTextContent("Scheduled");
    expect(block).toHaveAccessibleName(/REQ-7 Replace lights, Scheduled, 16 Nov, 09:00 to 10:00/);
    expect(url!.searchParams.get("from")).toBe("2026-11-15T18:00:00.000Z");
    expect(url!.searchParams.get("to")).toBe("2026-11-16T18:00:00.000Z");
    expect(within(screen.getByRole("region", { name: "Day schedule" })).getByText("Time off")).toBeInTheDocument();
  });

  it("flags conflicts with an icon and text", async () => {
    server.use(
      http.get(apiUrl("/technicians"), () => HttpResponse.json({ items: [], total: 0, page: 1, page_size: 100 })),
      http.get(apiUrl("/schedule"), () => HttpResponse.json(schedule(true))),
    );
    renderWithProviders(<SchedulePage />, { route: "/schedule", search: { date: "2026-11-16" } });
    const block = await screen.findByTestId("block-REQ-7");
    expect(block).toHaveTextContent("Conflict: overlap");
    expect(block).toHaveAccessibleName(/scheduling conflict/);
  });

  it("week view: puts the block in the Monday cell and requests 7 days", async () => {
    let url: URL | null = null;
    server.use(
      http.get(apiUrl("/technicians"), () => HttpResponse.json({ items: [], total: 0, page: 1, page_size: 100 })),
      http.get(apiUrl("/schedule"), ({ request }) => {
        url = new URL(request.url);
        return HttpResponse.json(schedule());
      }),
    );
    renderWithProviders(<SchedulePage />, { route: "/schedule", search: { view: "week", date: "2026-11-18" } });
    const block = await screen.findByTestId("block-REQ-7");
    const cell = block.closest("[data-day]")!;
    expect(cell).toHaveAttribute("data-day", "2026-11-16");
    expect(within(screen.getByRole("region", { name: "Week schedule" })).getAllByText(/^Mon 16 Nov$/)).toHaveLength(1);
    expect(url!.searchParams.get("from")).toBe("2026-11-15T18:00:00.000Z");
    expect(url!.searchParams.get("to")).toBe("2026-11-22T18:00:00.000Z");
  });
});
