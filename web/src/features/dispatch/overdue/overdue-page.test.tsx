import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { renderWithProviders } from "@/test/render";
import { apiUrl, http, HttpResponse, server } from "@/test/server";
import { OverduePage } from "./overdue-page";

const item = (n: number, status: string, extra: Record<string, unknown> = {}) => ({
  id: `r${n}`,
  number: n,
  display_id: `REQ-${n}`,
  title: `Thing ${n}`,
  status,
  priority: "HIGH",
  category: { id: "c1", name: "HVAC" },
  property: { id: "p1", name: "Orion Clinic", address: "x" },
  asset: null,
  requester: null,
  created_at: "2026-11-10T00:00:00Z",
  updated_at: "2026-11-10T00:00:00Z",
  sla_state: "OVERDUE",
  sla_due_at: "2026-11-14T00:00:00Z",
  overdue_by_minutes: 120,
  escalated_at: null,
  technician: null,
  appointment: null,
  ...extra,
});

describe("OverduePage", () => {
  it("Smart assign only for TRIAGED; Triage for SUBMITTED; Open otherwise; shows technician", async () => {
    server.use(
      http.get(apiUrl("/dashboard/overdue"), () =>
        HttpResponse.json({
          count: 3,
          page: 1,
          page_size: 50,
          items: [
            item(41, "SUBMITTED"),
            item(42, "TRIAGED"),
            item(43, "SCHEDULED", { technician: { membership_id: "t1", name: "Tech One" }, appointment: { start_at: "2026-11-18T08:00:00Z", end_at: "2026-11-18T09:00:00Z" } }),
          ],
        }),
      ),
      http.get(apiUrl("/requests"), () => HttpResponse.json({ items: [], total: 0, page: 1, page_size: 50 })),
    );
    renderWithProviders(<OverduePage />, { route: "/overdue" });
    expect(await screen.findByRole("link", { name: "Triage REQ-41" })).toHaveAttribute("href", "/requests/r41#triage");
    expect(screen.queryByRole("link", { name: "Smart assign REQ-41" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Smart assign REQ-42" })).toHaveAttribute("href", "/requests/r42#assign");
    expect(screen.getByRole("link", { name: "Open REQ-43" })).toHaveAttribute("href", "/requests/r43");
    expect(screen.getByText(/Tech One/)).toBeInTheDocument();
    expect(screen.getAllByText(/Unassigned/).length).toBeGreaterThan(0);
  });
});
