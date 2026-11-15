import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import NotificationsPage from "@/app/(app)/notifications/page";
import { renderWithProviders } from "@/test/render";
import { apiUrl, http, HttpResponse, server } from "@/test/server";

function seed() {
  const items = [
    { id: "n1", type: "REQUEST_ASSIGNED", title: "Technician assigned", body: "REQ-7 scheduled", request_id: "r7", data: null, read_at: null as string | null, created_at: "2026-11-15T05:00:00Z" },
    { id: "n2", type: "ESTIMATE_SUBMITTED", title: "Estimate ready", body: "REQ-9", request_id: "r9", data: null, read_at: null as string | null, created_at: "2026-11-15T04:00:00Z" },
  ];
  server.use(
    http.get(apiUrl("/notifications/unread-count"), () => HttpResponse.json({ unread: items.filter((i) => !i.read_at).length })),
    http.get(apiUrl("/notifications"), ({ request }) => {
      const unreadOnly = new URL(request.url).searchParams.get("unread_only") === "true";
      const list = unreadOnly ? items.filter((i) => !i.read_at) : items;
      return HttpResponse.json({ items: list, total: list.length, page: 1, page_size: 20 });
    }),
    http.post(apiUrl("/notifications/:id/read"), ({ params }) => {
      const n = items.find((i) => i.id === params.id)!;
      n.read_at = "2026-11-15T06:00:00Z";
      return HttpResponse.json(n);
    }),
    http.post(apiUrl("/notifications/read-all"), () => {
      items.forEach((i) => (i.read_at ??= "2026-11-15T06:00:00Z"));
      return HttpResponse.json({ updated: 2 });
    }),
  );
}

describe("notifications page", () => {
  it("marking one as read invalidates and the unread count updates from the backend", async () => {
    seed();
    renderWithProviders(<NotificationsPage />);
    expect(await screen.findByText("2 unread")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: 'Mark "Technician assigned" as read' }));
    expect(await screen.findByText("1 unread")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: 'Mark "Technician assigned" as read' })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: 'Mark "Estimate ready" as read' })).toBeInTheDocument();
  });

  it("mark all read empties the unread count and links to the request", async () => {
    seed();
    renderWithProviders(<NotificationsPage />);
    const link = (await screen.findAllByRole("link", { name: "Open request" }))[0]!;
    expect(link).toHaveAttribute("href", "/requests/r7");
    await userEvent.click(screen.getByRole("button", { name: /Mark all read/ }));
    await waitFor(() => expect(screen.getByText("You are all caught up")).toBeInTheDocument());
  });

  it("unread filter asks the API for unread only", async () => {
    seed();
    renderWithProviders(<NotificationsPage />);
    await screen.findByText("Technician assigned");
    await userEvent.click(screen.getByRole("switch", { name: "Unread only" }));
    await userEvent.click(within(screen.getByText("Technician assigned").closest("li")!).getByRole("button", { name: /Mark/ }));
    await waitFor(() => expect(screen.queryByText("Technician assigned")).not.toBeInTheDocument());
    expect(screen.getByText("Estimate ready")).toBeInTheDocument();
  });
});
