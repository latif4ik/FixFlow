import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { mockRouter } from "@/test/navigation-mock";
import { fakeSession, renderWithProviders } from "@/test/render";
import { apiUrl, http, HttpResponse, server } from "@/test/server";
import { DashboardPage } from "./dashboard-page";

const summary = {
  range: { from_date: "2026-10-17", to_date: "2026-11-15", start_at: "2026-10-16T18:00:00Z", end_at: "2026-11-15T18:00:00Z", timezone: "Asia/Bishkek" },
  counts_by_status: { SUBMITTED: 7, TRIAGED: 6, SCHEDULED: 4, IN_PROGRESS: 2 },
  open_requests: 31,
  overdue_requests: 4,
  upcoming_appointments: 9,
  completed_in_range: 17,
  technician_utilization: {
    percent: 140,
    percent_capped: 100,
    planned_minutes: 1400,
    available_minutes: 1000,
    explanation: "Utilization = planned minutes / available minutes (test explanation).",
    per_technician: [],
  },
  approved_estimates_total_minor: 1156500,
  approved_estimates_label: "approved estimates (not collected revenue)",
  material_costs_total_minor: 991700,
  currency: "KGS",
};

const daily = Array.from({ length: 14 }, (_, i) => ({ date: `2026-11-${String(i + 2).padStart(2, "0")}`, new_requests: 2, completed_requests: i === 0 ? 5 : 1 }));
// totals: new 28, completed 5 + 13 = 18

const overdueItem = (id: string, n: number, status: string) => ({
  id,
  number: n,
  display_id: `REQ-${n}`,
  title: `Overdue thing ${n}`,
  status,
  priority: "HIGH",
  category: { id: "c1", name: "HVAC" },
  property: { id: "p1", name: "Orion Clinic", address: "x" },
  asset: null,
  requester: null,
  created_at: "2026-11-10T00:00:00Z",
  updated_at: "2026-11-10T00:00:00Z",
  overdue_by_minutes: 125,
});

function seed(captured: URL[] = []) {
  server.use(
    http.get(apiUrl("/reports/summary"), ({ request }) => {
      captured.push(new URL(request.url));
      return HttpResponse.json(summary);
    }),
    http.get(apiUrl("/reports/daily"), () => HttpResponse.json(daily)),
    http.get(apiUrl("/reports/distribution"), () => HttpResponse.json([{ key: "HIGH", label: "High", count: 3 }])),
    http.get(apiUrl("/dashboard/overdue"), () => HttpResponse.json({ count: 5, page: 1, page_size: 3, items: [overdueItem("r41", 41, "TRIAGED"), overdueItem("r42", 42, "IN_PROGRESS")] })),
    http.get(apiUrl("/requests"), ({ request }) => {
      const u = new URL(request.url);
      if (u.searchParams.get("sla_state") === "AT_RISK") return HttpResponse.json({ items: [], total: 7, page: 1, page_size: 100 });
      return HttpResponse.json({ items: [], total: 9, page: 1, page_size: 1 });
    }),
    http.get(apiUrl("/schedule"), () => HttpResponse.json({ range: { from: "", to: "", timezone: "Asia/Bishkek" }, technicians: [] })),
    http.get(apiUrl("/categories"), () => HttpResponse.json({ items: [{ id: "c1", name: "HVAC" }, { id: "c2", name: "Plumbing" }], total: 2, page: 1, page_size: 100 })),
    http.get(apiUrl("/technicians"), () => HttpResponse.json({ items: [{ membership_id: "t1", full_name: "Tech One" }], total: 1, page: 1, page_size: 100 })),
  );
}

describe("dashboard", () => {
  it("renders KPI values from the summary, the sentence, overdue actions and chart legend totals", async () => {
    seed();
    renderWithProviders(<DashboardPage />, { session: fakeSession({ role: "DISPATCHER" }) });
    await waitFor(() => expect(screen.getByText("31")).toBeInTheDocument()); // open requests
    const dl = screen.getByLabelText("Totals");
    expect(within(dl).getByText("Open requests")).toBeInTheDocument();
    expect(within(dl).getByText("17")).toBeInTheDocument(); // completed in range
    expect(within(dl).getByText("9", { selector: "dd" })).toBeInTheDocument(); // upcoming
    expect(await screen.findByText("5 requests are overdue and 9 are waiting for a technician.")).toBeInTheDocument();

    // legend shows range totals with units
    const legend = await screen.findByLabelText("Legend with totals for the range");
    expect(legend).toHaveTextContent("New requests: 28 in range");
    expect(legend).toHaveTextContent("Completed: 18 in range");

    // utilization: capped value, raw note and API explanation
    expect(await screen.findByText("100%")).toBeInTheDocument();
    expect(screen.getByText(/Raw utilization is 140%/)).toBeInTheDocument();
    expect(screen.getByText(/test explanation/)).toBeInTheDocument();
    expect(screen.getByText("Estimates, not collected revenue")).toBeInTheDocument();

    // overdue panel: unassigned -> Smart assign deep link, in progress -> Open
    expect(screen.getByRole("link", { name: /Smart assign REQ-41/ })).toHaveAttribute("href", "/requests/r41#assign");
    expect(screen.getByRole("link", { name: /Open REQ-42/ })).toHaveAttribute("href", "/requests/r42");
    expect(screen.getByRole("link", { name: "Review all 5 overdue requests" })).toHaveAttribute("href", "/overdue");
  });

  it("sends the URL filters to /reports/summary and writes changes back to the URL", async () => {
    const captured: URL[] = [];
    seed(captured);
    renderWithProviders(<DashboardPage />, { route: "/dashboard", search: { from: "2026-11-01", to: "2026-11-14", category_id: "c1" } });
    await waitFor(() => expect(captured.length).toBeGreaterThan(0));
    const q = captured[0]!.searchParams;
    expect(q.get("from")).toBe("2026-11-01");
    expect(q.get("to")).toBe("2026-11-14");
    expect(q.get("category_id")).toBe("c1");
    expect(q.get("technician_id")).toBeNull();

    const user = userEvent.setup();
    await screen.findByRole("option", { name: "Tech One" });
    await user.selectOptions(screen.getByLabelText("Technician"), "t1");
    expect(mockRouter.replace).toHaveBeenCalledWith(expect.stringContaining("technician_id=t1"));
    expect(mockRouter.replace).toHaveBeenCalledWith(expect.stringContaining("category_id=c1"));
  });

  it("offers Triage (not Smart assign) for SUBMITTED overdue requests and shows property, technician and appointment", async () => {
    seed();
    const tech = { membership_id: "t1", name: "Tech One" };
    server.use(
      http.get(apiUrl("/dashboard/overdue"), () =>
        HttpResponse.json({
          count: 2,
          page: 1,
          page_size: 3,
          items: [
            overdueItem("r41", 41, "SUBMITTED"),
            { ...overdueItem("r44", 44, "SCHEDULED"), technician: tech, appointment: { start_at: "2026-11-18T08:00:00Z", end_at: "2026-11-18T09:00:00Z" } },
          ],
        }),
      ),
    );
    renderWithProviders(<DashboardPage />, { session: fakeSession({ role: "DISPATCHER" }) });
    const triage = await screen.findByRole("link", { name: /Triage REQ-41/ });
    expect(triage).toHaveAttribute("href", "/requests/r41#triage");
    expect(screen.queryByRole("link", { name: /Smart assign REQ-41/ })).not.toBeInTheDocument();
    expect(screen.getByText(/Orion Clinic · Unassigned/)).toBeInTheDocument();
    expect(screen.getByText(/Orion Clinic · Tech One/)).toBeInTheDocument();
    expect(screen.getByText(/18 Nov, 14:00/)).toBeInTheDocument();
  });
});
