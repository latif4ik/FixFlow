import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { fakeSession, renderWithProviders } from "@/test/render";
import { apiUrl, http, HttpResponse, server } from "@/test/server";
import { MaintenancePage } from "./maintenance-page";

const plan = {
  id: "p1",
  asset: { id: "a1", code: "BOILER-1", name: "Main boiler", status: "ACTIVE" },
  category: { id: "c1", name: "General maintenance" },
  title: "Monthly boiler inspection",
  description: "Routine preventive maintenance as per the manufacturer schedule.",
  priority: "HIGH",
  first_date: "2026-11-25",
  recurrence: "MONTHLY",
  is_enabled: true,
  last_generated_for: null,
  next_occurrence: "2026-11-25",
};

describe("maintenance page", () => {
  it("lists plans with next occurrence and posts Generate now with as_of and an Idempotency-Key", async () => {
    const calls: { body: unknown; key: string | null }[] = [];
    server.use(
      http.get(apiUrl("/maintenance-plans"), () => HttpResponse.json({ items: [plan], total: 1, page: 1, page_size: 20 })),
      http.post(apiUrl("/maintenance-plans/generate"), async ({ request }) => {
        calls.push({ body: await request.json(), key: request.headers.get("Idempotency-Key") });
        return HttpResponse.json({ as_of: "2026-12-01", plans_processed: 1, requests_created: 3, skipped_existing: 1, errors: 0, plans: [] });
      }),
    );
    renderWithProviders(<MaintenancePage />, { session: fakeSession({ role: "ADMIN" }) });
    const user = userEvent.setup();
    expect(await screen.findByText("Monthly boiler inspection")).toBeInTheDocument();
    expect(screen.getAllByText("25 Nov 2026").length).toBe(2); // first date + next occurrence

    const date = screen.getByLabelText("As of date");
    await user.clear(date);
    await user.type(date, "2026-12-01");
    await user.click(screen.getByRole("button", { name: "Generate now" }));
    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0]!.body).toEqual({ as_of: "2026-12-01" });
    expect(calls[0]!.key).toBeTruthy();
    expect(await screen.findByRole("status")).toHaveTextContent("3 requests created for 2026-12-01; 1 already existed");
  });

  it("requires a 20+ character description when creating a plan", async () => {
    server.use(
      http.get(apiUrl("/maintenance-plans"), () => HttpResponse.json({ items: [], total: 0, page: 1, page_size: 20 })),
      http.get(apiUrl("/assets"), () => HttpResponse.json({ items: [], total: 0, page: 1, page_size: 100 })),
      http.get(apiUrl("/categories"), () => HttpResponse.json({ items: [], total: 0, page: 1, page_size: 100 })),
    );
    renderWithProviders(<MaintenancePage />, { session: fakeSession({ role: "ADMIN" }) });
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: /New plan/ }));
    await user.type(await screen.findByLabelText(/^Description/), "too short");
    await user.click(screen.getByRole("button", { name: "Create plan" }));
    expect(await screen.findByText("Describe the work in at least 20 characters.")).toBeInTheDocument();
    expect(screen.getByText("Choose an asset.")).toBeInTheDocument();
  });
});
