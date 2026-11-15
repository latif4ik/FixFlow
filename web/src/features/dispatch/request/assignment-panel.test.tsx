import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { renderWithProviders } from "@/test/render";
import { apiUrl, errorResponse, http, HttpResponse, server } from "@/test/server";
import { CATEGORY_HVAC, makeCtx } from "../fixtures";
import { AssignmentPanel } from "./assignment-panel";

const TECH = { membership_id: "t3", name: "Technician Three" };
const suggestions = {
  request_id: "r1",
  duration_minutes: 90,
  horizon: { from: "2026-11-15T00:30:00Z", to: "2026-11-29T00:00:00Z" },
  suggestions: [
    // 11:00-12:30 local, ends well before due 11:00Z (17:00 local)
    { technician: TECH, start_at: "2026-11-16T05:00:00Z", end_at: "2026-11-16T06:30:00Z", workload_minutes_next_7_days: 360, sla: { due_at: "2026-11-16T11:00:00Z", slot_ends_after_due: false }, reason: "Earliest free slot" },
    // 16:00-17:30 local, ends after due
    { technician: TECH, start_at: "2026-11-16T10:00:00Z", end_at: "2026-11-16T11:30:00Z", workload_minutes_next_7_days: 360, sla: { due_at: "2026-11-16T11:00:00Z", slot_ends_after_due: true }, reason: "Alternative slot" },
  ],
  skipped: [],
  unskilled_technicians: 3,
};

function baseHandlers(calls: { suggest: number } = { suggest: 0 }) {
  server.use(
    http.get(apiUrl("/categories"), () => HttpResponse.json({ items: [CATEGORY_HVAC], total: 1, page: 1, page_size: 100 })),
    http.get(apiUrl("/requests/r1/assignments"), () => HttpResponse.json([])),
    http.get(apiUrl("/requests/r1/suggestions"), () => {
      calls.suggest += 1;
      return HttpResponse.json(suggestions);
    }),
  );
  return calls;
}

describe("Smart Assign panel", () => {
  it("shows suggested slots with technician, org-local window and Within/Breaches SLA text", async () => {
    baseHandlers();
    renderWithProviders(<AssignmentPanel ctx={makeCtx()} />);
    expect(await screen.findByText(/HVAC jobs default to 1 h 30 min/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Suggest slots/ }));
    // window 11:00-18:00 local (Asia/Bishkek) contains the 11:00 slot; the 16:00 slot also fits
    const within_ = await screen.findByText(/Within SLA\./);
    expect(within_).toHaveTextContent("Slot ends 4 h 30 min before the SLA due time");
    expect(screen.getByText(/Breaches SLA\./)).toHaveTextContent("Slot ends 30 min after the SLA due time");
    expect(screen.getAllByText("Technician Three").length).toBeGreaterThan(0);
    expect(screen.getByText("16 Nov, 11:00 - 12:30")).toBeInTheDocument();
    expect(screen.getByText("Earliest free slot · 6 h booked in the next 7 days")).toBeInTheDocument();
  });

  it("sends the chosen window (org tz -> UTC) as from/to, and 'Show all' calls without them", async () => {
    const seen: URL[] = [];
    server.use(
      http.get(apiUrl("/categories"), () => HttpResponse.json({ items: [CATEGORY_HVAC], total: 1, page: 1, page_size: 100 })),
      http.get(apiUrl("/requests/r1/assignments"), () => HttpResponse.json([])),
      http.get(apiUrl("/requests/r1/suggestions"), ({ request }) => {
        const u = new URL(request.url);
        seen.push(u);
        return HttpResponse.json(u.searchParams.has("from") ? { ...suggestions, suggestions: [] } : suggestions);
      }),
    );
    renderWithProviders(<AssignmentPanel ctx={makeCtx()} />);
    const date = await screen.findByLabelText("Date");
    await userEvent.clear(date);
    await userEvent.type(date, "2026-11-18");
    const start = screen.getByLabelText("Earliest start");
    await userEvent.clear(start);
    await userEvent.type(start, "14:00");
    const end = screen.getByLabelText("Latest finish");
    await userEvent.clear(end);
    await userEvent.type(end, "18:00");
    await userEvent.click(screen.getByRole("button", { name: /Suggest slots/ }));
    expect(await screen.findByText("No slots inside this window")).toBeInTheDocument();
    // 14:00-18:00 Asia/Bishkek (UTC+6) = 08:00-12:00Z
    expect(seen[0]!.searchParams.get("from")).toBe("2026-11-18T08:00:00.000Z");
    expect(seen[0]!.searchParams.get("to")).toBe("2026-11-18T12:00:00.000Z");
    expect(seen[0]!.searchParams.has("horizon_days")).toBe(false);
    await userEvent.click(screen.getByRole("button", { name: "Show all suggestions" }));
    expect(await screen.findByText("16 Nov, 11:00 - 12:30")).toBeInTheDocument();
    const last = seen.at(-1)!;
    expect(last.searchParams.has("from")).toBe(false);
    expect(last.searchParams.has("to")).toBe(false);
  });

  it("assigns through POST /assignment with an Idempotency-Key and the slot's exact window", async () => {
    baseHandlers();
    let seen: { key: string | null; body: unknown } | null = null;
    server.use(
      http.post(apiUrl("/requests/r1/assignment"), async ({ request }) => {
        seen = { key: request.headers.get("Idempotency-Key"), body: await request.json() };
        return HttpResponse.json({ assignment: {}, request: {} }, { status: 201 });
      }),
    );
    renderWithProviders(<AssignmentPanel ctx={makeCtx()} />);
    await userEvent.click(await screen.findByRole("button", { name: /Suggest slots/ }));
    await userEvent.click(await screen.findByRole("button", { name: "Assign Technician Three, 16 Nov, 11:00 - 12:30" }));
    await waitFor(() => expect(seen).not.toBeNull());
    expect(seen!.key).toMatch(/^[0-9a-f-]{36}$/);
    expect(seen!.body).toEqual({ technician_membership_id: "t3", start_at: "2026-11-16T05:00:00Z", end_at: "2026-11-16T06:30:00Z" });
  });

  it("shows 'Slot just taken' on a 409 and refetches suggestions when asked to refresh", async () => {
    const calls = baseHandlers();
    server.use(http.post(apiUrl("/requests/r1/assignment"), () => errorResponse(409, "schedule_conflict", "The technician was just booked for an overlapping time. Pick another slot.")));
    renderWithProviders(<AssignmentPanel ctx={makeCtx()} />);
    await userEvent.click(await screen.findByRole("button", { name: /Suggest slots/ }));
    await userEvent.click(await screen.findByRole("button", { name: /^Assign Technician Three, 16 Nov, 11:00/ }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Slot just taken — refresh suggestions");
    expect(alert).toHaveTextContent("just booked for an overlapping time");
    const before = calls.suggest;
    await userEvent.click(within(alert).getByRole("button", { name: /Refresh suggestions/ }));
    await waitFor(() => expect(calls.suggest).toBe(before + 1));
    await waitFor(() => expect(screen.queryByText(/Slot just taken/)).not.toBeInTheDocument());
  });

  it("manual mode lists candidates with ineligibility reasons and only offers Assign to eligible ones", async () => {
    baseHandlers();
    server.use(
      http.get(apiUrl("/requests/r1/candidates"), ({ request }) => {
        const u = new URL(request.url);
        expect(u.searchParams.get("start_at")).toBe("2026-11-16T05:00:00.000Z");
        expect(u.searchParams.get("end_at")).toBe("2026-11-16T06:30:00.000Z");
        return HttpResponse.json([
          { membership_id: "t1", name: "Technician One", skills: ["electrical"], eligible: false, available: false, workload: { active_assignments: 3, planned_minutes_next_7_days: 210 }, reasons: [{ code: "missing_skills", message: "The technician lacks required skills: hvac." }, { code: "overlap", message: "overlap", details: { assignments: [{ display_id: "REQ-7" }] } }] },
          { membership_id: "t4", name: "Technician Four", skills: ["hvac"], eligible: false, available: false, workload: { active_assignments: 0, planned_minutes_next_7_days: 0 }, reasons: [{ code: "time_off", message: "The technician has time off in this window." }] },
          { membership_id: "t3", name: "Technician Three", skills: ["hvac"], eligible: true, available: true, workload: { active_assignments: 1, planned_minutes_next_7_days: 90 }, reasons: [] },
        ]);
      }),
    );
    renderWithProviders(<AssignmentPanel ctx={makeCtx()} />);
    await userEvent.click(await screen.findByRole("button", { name: "Pick manually" }));
    const list = await screen.findByRole("list", { name: "Technician eligibility" });
    const rows = within(list).getAllByRole("listitem");
    expect(rows).toHaveLength(3);
    expect(within(rows[0]!).getByText("The technician lacks required skills: hvac.")).toBeInTheDocument();
    expect(within(rows[0]!).getByText("Overlaps REQ-7")).toBeInTheDocument();
    expect(within(rows[0]!).getByText("Skills 0 of 1")).toBeInTheDocument();
    expect(within(rows[0]!).getByText("Not eligible")).toBeInTheDocument();
    expect(within(rows[1]!).getByText("The technician has time off in this window.")).toBeInTheDocument();
    expect(within(rows[2]!).getByText("Eligible")).toBeInTheDocument();
    expect(within(list).getAllByRole("button", { name: /^Assign / })).toHaveLength(1);
  });

  it("unassign needs a reason, then POSTs it", async () => {
    server.use(
      http.get(apiUrl("/requests/r1/assignments"), () => HttpResponse.json([])),
    );
    let body: unknown = null;
    server.use(
      http.post(apiUrl("/requests/r1/assignment/unassign"), async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ ok: true });
      }),
    );
    const ctx = makeCtx({
      status: "SCHEDULED",
      allowed_actions: ["unassign", "reschedule", "add_note"],
      assignment: { id: "a1", technician: TECH, start_at: "2026-11-16T05:00:00Z", end_at: "2026-11-16T06:30:00Z", status: "ACTIVE" },
    });
    renderWithProviders(<AssignmentPanel ctx={ctx} />);
    expect(screen.getByText("16 Nov, 11:00 - 12:30")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /^Unassign$/ }));
    const dialog = await screen.findByRole("alertdialog");
    expect(dialog).toHaveTextContent("The request goes back to Triaged and the technician is notified.");
    const confirm = within(dialog).getByRole("button", { name: "Unassign" });
    expect(confirm).toBeDisabled();
    await userEvent.type(within(dialog).getByLabelText(/Reason/), "abc");
    expect(confirm).toBeDisabled();
    await userEvent.type(within(dialog).getByLabelText(/Reason/), "de sick");
    expect(confirm).toBeEnabled();
    await userEvent.click(confirm);
    await waitFor(() => expect(body).toEqual({ reason: "abcde sick" }));
  });

  it("reschedule reuses the picker and sends PUT", async () => {
    baseHandlers();
    let method = "";
    server.use(
      http.put(apiUrl("/requests/r1/assignment"), ({ request }) => {
        method = request.method;
        return HttpResponse.json({ assignment: {}, request: {} });
      }),
    );
    const ctx = makeCtx({
      status: "SCHEDULED",
      allowed_actions: ["unassign", "reschedule"],
      assignment: { id: "a1", technician: TECH, start_at: "2026-11-16T05:00:00Z", end_at: "2026-11-16T06:30:00Z", status: "ACTIVE" },
    });
    renderWithProviders(<AssignmentPanel ctx={ctx} />);
    await userEvent.click(screen.getByRole("button", { name: /^Reschedule$/ }));
    await userEvent.click(await screen.findByRole("button", { name: /Suggest slots/ }));
    await userEvent.click(await screen.findByRole("button", { name: /^Reschedule Technician Three, 16 Nov, 11:00/ }));
    await waitFor(() => expect(method).toBe("PUT"));
  });
});
