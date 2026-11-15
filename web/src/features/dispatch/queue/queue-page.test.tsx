import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { mockRouter } from "@/test/navigation-mock";
import { renderWithProviders } from "@/test/render";
import { apiUrl, http, HttpResponse, server } from "@/test/server";
import { filtersFromSearch, toApiParams, QueuePage } from "./queue-page";

const item = (n: number, over: Record<string, unknown> = {}) => ({
  id: `id-${n}`,
  number: n,
  display_id: `REQ-${n}`,
  title: `Request ${n}`,
  status: "TRIAGED",
  priority: "HIGH",
  category: { id: "c1", name: "HVAC" },
  property: { id: "p1", name: "HQ Tower", address: "1 Main" },
  asset: null,
  requester: null,
  created_at: "2026-11-14T10:00:00Z",
  updated_at: "2026-11-14T10:00:00Z",
  sla_state: "AT_RISK",
  sla_due_at: "2026-11-16T11:00:00Z",
  ...over,
});

function setup() {
  const seen: URL[] = [];
  server.use(
    http.get(apiUrl("/requests"), ({ request }) => {
      seen.push(new URL(request.url));
      return HttpResponse.json({ items: [item(14), item(15, { status: "SUBMITTED" })], total: 45, page: Number(new URL(request.url).searchParams.get("page") ?? 1), page_size: 20 });
    }),
    http.get(apiUrl("/categories"), () => HttpResponse.json({ items: [{ id: "c1", name: "HVAC" }], total: 1, page: 1, page_size: 100 })),
    http.get(apiUrl("/properties"), () => HttpResponse.json({ items: [{ id: "p1", name: "HQ Tower" }], total: 1, page: 1, page_size: 100 })),
    http.get(apiUrl("/technicians"), () => HttpResponse.json({ items: [{ membership_id: "t1", full_name: "Tech One" }], total: 1, page: 1, page_size: 100 })),
  );
  return seen;
}

describe("queue URL <-> API params", () => {
  it("round-trips filters", () => {
    const f = filtersFromSearch(new URLSearchParams("q=pump&status=TRIAGED&status=SCHEDULED&sla_state=OVERDUE&sort=due&page=3"));
    expect(toApiParams(f)).toEqual({
      q: "pump",
      status: ["TRIAGED", "SCHEDULED"],
      priority: undefined,
      category_id: undefined,
      property_id: undefined,
      technician_id: undefined,
      sla_state: ["OVERDUE"],
      sort: "due",
      page: 3,
    });
  });
});

describe("QueuePage", () => {
  it("sends URL filters to the API with server paging and renders rows linking to the request", async () => {
    const seen = setup();
    renderWithProviders(<QueuePage />, { route: "/queue", search: { q: "chiller", status: "TRIAGED", priority: "HIGH", sort: "due" } });
    const table = await screen.findByRole("region", { name: "Requests" });
    expect(await within(table).findByRole("link", { name: "REQ-14" })).toHaveAttribute("href", "/requests/id-14");
    const u = seen[seen.length - 1]!;
    expect(u.searchParams.get("q")).toBe("chiller");
    expect(u.searchParams.getAll("status")).toEqual(["TRIAGED"]);
    expect(u.searchParams.get("priority")).toBe("HIGH");
    expect(u.searchParams.get("sort")).toBe("due");
    expect(u.searchParams.get("page_size")).toBe("20");
    expect(screen.getByRole("searchbox")).toHaveValue("chiller");
    expect(screen.getByText("1-20 of 45")).toBeInTheDocument();
  });

  it("writes the search term to the URL on submit (page resets)", async () => {
    setup();
    renderWithProviders(<QueuePage />, { route: "/queue", search: { page: "2" } });
    await screen.findByText("REQ-14");
    await userEvent.type(screen.getByRole("searchbox"), "air handler");
    await userEvent.click(screen.getByRole("button", { name: "Search" }));
    expect(mockRouter.replace).toHaveBeenLastCalledWith("/queue?q=air+handler");
  });

  it("quick filters set status / SLA state in the URL, and paging keeps filters", async () => {
    setup();
    renderWithProviders(<QueuePage />, { route: "/queue", search: { priority: "LOW" } });
    await screen.findByText("REQ-14");
    await userEvent.click(screen.getByRole("button", { name: "Unassigned" }));
    expect(mockRouter.replace).toHaveBeenLastCalledWith("/queue?status=TRIAGED&priority=LOW");
    await userEvent.click(screen.getByRole("button", { name: "Overdue" }));
    expect(mockRouter.replace).toHaveBeenLastCalledWith("/queue?priority=LOW&sla_state=OVERDUE");
    await userEvent.click(screen.getByRole("button", { name: "Next page" }));
    expect(mockRouter.replace).toHaveBeenLastCalledWith("/queue?priority=LOW&page=2");
  });

  it("changing the sort select and the technician select updates the URL", async () => {
    setup();
    renderWithProviders(<QueuePage />, { route: "/queue" });
    await screen.findByText("REQ-14");
    await screen.findByRole("option", { name: "Tech One" });
    await userEvent.selectOptions(screen.getByLabelText("Sort by"), "priority");
    expect(mockRouter.replace).toHaveBeenLastCalledWith("/queue?sort=priority");
    await userEvent.selectOptions(screen.getByLabelText("Technician"), "t1");
    expect(mockRouter.replace).toHaveBeenLastCalledWith("/queue?technician_id=t1");
  });

  it("shows Technician and Appointment columns in the org timezone", async () => {
    server.use(
      http.get(apiUrl("/requests"), () =>
        HttpResponse.json({
          items: [item(14, { technician: { membership_id: "t1", name: "Tech One" }, appointment: { start_at: "2026-11-18T09:00:00Z", end_at: "2026-11-18T10:30:00Z" } }), item(15)],
          total: 2,
          page: 1,
          page_size: 20,
        }),
      ),
      http.get(apiUrl("/categories"), () => HttpResponse.json({ items: [], total: 0, page: 1, page_size: 100 })),
      http.get(apiUrl("/properties"), () => HttpResponse.json({ items: [], total: 0, page: 1, page_size: 100 })),
      http.get(apiUrl("/technicians"), () => HttpResponse.json({ items: [], total: 0, page: 1, page_size: 100 })),
    );
    renderWithProviders(<QueuePage />, { route: "/queue" });
    const table = await screen.findByRole("region", { name: "Requests" });
    expect(await within(table).findByRole("columnheader", { name: "Technician" })).toBeInTheDocument();
    expect(within(table).getByRole("columnheader", { name: "Appointment" })).toBeInTheDocument();
    expect(within(table).getByText("Tech One")).toBeInTheDocument();
    expect(within(table).getByText(/18 Nov, 15:00/)).toBeInTheDocument(); // 09:00Z in Asia/Bishkek
    expect(within(table).getByText("Unassigned")).toBeInTheDocument();
  });
});
