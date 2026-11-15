import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { mockRouter } from "@/test/navigation-mock";
import { fakeSession, renderWithProviders } from "@/test/render";
import { apiUrl, http, HttpResponse, server } from "@/test/server";
import { MyRequestsPage } from "./my-requests-page";

const item = {
  id: "r1",
  number: 1,
  display_id: "REQ-1",
  title: "Leaking tap in the kitchen",
  status: "SUBMITTED",
  priority: "HIGH",
  category: { id: "c", name: "Plumbing" },
  property: { id: "p", name: "Northwind HQ Tower", address: "1 Main" },
  asset: null,
  requester: null,
  created_at: "2026-11-15T03:02:00Z",
  updated_at: "2026-11-15T03:02:00Z",
};
const session = () => fakeSession({ role: "REQUESTER" });

describe("My requests", () => {
  it("lists requests with link, status and property, and sends URL filters to the API", async () => {
    const urls: URL[] = [];
    server.use(
      http.get(apiUrl("/requests"), ({ request }) => {
        urls.push(new URL(request.url));
        return HttpResponse.json({ items: [item], total: 1, page: 1, page_size: 20 });
      }),
    );
    renderWithProviders(<MyRequestsPage />, { session: session(), route: "/requests", search: { q: "tap", status: "SUBMITTED", sort: "oldest" } });
    const link = await screen.findByRole("link", { name: "Leaking tap in the kitchen" });
    expect(link).toHaveAttribute("href", "/requests/r1");
    expect(screen.getByText("Northwind HQ Tower")).toBeInTheDocument();
    expect(screen.getByText("High priority")).toBeInTheDocument();
    const u = urls[0]!;
    expect(u.searchParams.get("q")).toBe("tap");
    expect(u.searchParams.getAll("status")).toEqual(["SUBMITTED"]);
    expect(u.searchParams.get("sort")).toBe("oldest");
    expect(u.searchParams.get("page_size")).toBe("20");
    expect(screen.getByRole("button", { name: "Submitted" })).toHaveAttribute("aria-pressed", "true");
  });

  it("writes search, status, priority and sort changes to the URL query string", async () => {
    server.use(http.get(apiUrl("/requests"), () => HttpResponse.json({ items: [item], total: 1, page: 1, page_size: 20 })));
    renderWithProviders(<MyRequestsPage />, { session: session(), route: "/requests" });
    await screen.findByRole("link", { name: "Leaking tap in the kitchen" });

    await userEvent.click(screen.getByRole("button", { name: "Completed" }));
    expect(mockRouter.replace).toHaveBeenLastCalledWith("/requests?status=COMPLETED");
    await userEvent.click(screen.getByRole("button", { name: "High" }));
    expect(mockRouter.replace).toHaveBeenLastCalledWith("/requests?priority=HIGH");
    await userEvent.selectOptions(screen.getByLabelText("Sort by"), "priority");
    expect(mockRouter.replace).toHaveBeenLastCalledWith("/requests?sort=priority");

    await userEvent.type(screen.getByLabelText("Search"), "boiler");
    await waitFor(() => expect(mockRouter.replace).toHaveBeenLastCalledWith("/requests?q=boiler"), { timeout: 2000 });
  });

  it("shows the empty state with a New request call to action when there are no requests", async () => {
    server.use(http.get(apiUrl("/requests"), () => HttpResponse.json({ items: [], total: 0, page: 1, page_size: 20 })));
    renderWithProviders(<MyRequestsPage />, { session: session(), route: "/requests" });
    expect(await screen.findByText("You have no requests yet")).toBeInTheDocument();
    const links = screen.getAllByRole("link", { name: /New request/ });
    expect(links.some((l) => l.getAttribute("href") === "/requests/new")).toBe(true);
  });

  it("shows a distinct empty-filter state with a way to clear", async () => {
    server.use(http.get(apiUrl("/requests"), () => HttpResponse.json({ items: [], total: 0, page: 1, page_size: 20 })));
    renderWithProviders(<MyRequestsPage />, { session: session(), route: "/requests", search: { q: "zzz" } });
    expect(await screen.findByText("No requests match these filters")).toBeInTheDocument();
    await userEvent.click(screen.getAllByRole("button", { name: "Clear filters" })[0]!);
    expect(mockRouter.replace).toHaveBeenLastCalledWith("/requests");
  });

  it("shows a retryable error state when the API fails", async () => {
    server.use(http.get(apiUrl("/requests"), () => HttpResponse.json({ error: { code: "internal", message: "Boom", details: null, request_id: "x" } }, { status: 500 })));
    renderWithProviders(<MyRequestsPage />, { session: session(), route: "/requests" });
    expect(await screen.findByText("Boom")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });
});
