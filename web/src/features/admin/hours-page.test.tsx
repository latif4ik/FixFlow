import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { fakeSession, renderWithProviders } from "@/test/render";
import { apiUrl, http, HttpResponse, server } from "@/test/server";
import { HoursPage } from "./hours-page";
import { validateIntervals } from "./week-editor";

function seed(puts: unknown[]) {
  server.use(
    http.get(apiUrl("/org/business-hours"), () => HttpResponse.json({ intervals: [{ weekday: 0, open_time: "09:00:00", close_time: "18:00:00" }] })),
    http.put(apiUrl("/org/business-hours"), async ({ request }) => {
      const body = await request.json();
      puts.push(body);
      return HttpResponse.json(body as Record<string, unknown>);
    }),
    http.get(apiUrl("/org/holidays"), () => HttpResponse.json({ items: [{ id: "h1", date: "2026-12-30", name: "Demo holiday" }], total: 1, page: 1, page_size: 100 })),
  );
}

describe("validateIntervals", () => {
  it("flags overlaps, inverted ranges and accepts touching intervals", () => {
    expect(validateIntervals([{ weekday: 1, start: "09:00", end: "12:00" }, { weekday: 1, start: "11:00", end: "15:00" }])[1]).toMatch(/overlap/i);
    expect(validateIntervals([{ weekday: 2, start: "12:00", end: "09:00" }])[2]).toMatch(/end after/i);
    expect(validateIntervals([{ weekday: 3, start: "09:00", end: "12:00" }, { weekday: 3, start: "12:00", end: "15:00" }])).toEqual({});
  });
});

describe("business hours editor", () => {
  it("rejects overlapping intervals (no request is sent) and saves once the overlap is removed", async () => {
    const puts: Array<{ intervals: Array<{ weekday: number; open_time: string; close_time: string }> }> = [];
    seed(puts);
    renderWithProviders(<HoursPage />, { session: fakeSession({ role: "ADMIN" }) });
    const user = userEvent.setup();
    await screen.findByLabelText("Monday interval 1 start");
    expect(screen.getByText("Demo holiday")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Add interval on Monday" })); // defaults to 09:00-18:00: overlaps
    expect(await screen.findByRole("alert")).toHaveTextContent(/Monday: Intervals overlap/);
    await user.click(screen.getByRole("button", { name: "Save business hours" }));
    expect(puts).toHaveLength(0);

    await user.click(screen.getByRole("button", { name: "Remove Monday interval 2" }));
    expect(screen.queryByText(/Intervals overlap/)).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Save business hours" }));
    await vi.waitFor(() => expect(puts).toHaveLength(1));
    expect(puts[0]!.intervals).toEqual([{ weekday: 0, open_time: "09:00:00", close_time: "18:00:00" }]);
  });

  it("asks for confirmation before deleting a holiday", async () => {
    const deleted: string[] = [];
    seed([]);
    server.use(
      http.delete(apiUrl("/org/holidays/:id"), ({ params }) => {
        deleted.push(String(params.id));
        return new HttpResponse(null, { status: 204 });
      }),
    );
    renderWithProviders(<HoursPage />, { session: fakeSession({ role: "ADMIN" }) });
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Delete holiday Demo holiday" }));
    expect(deleted).toHaveLength(0);
    await user.click(await screen.findByRole("button", { name: "Delete holiday" }));
    await vi.waitFor(() => expect(deleted).toEqual(["h1"]));
  });
});
