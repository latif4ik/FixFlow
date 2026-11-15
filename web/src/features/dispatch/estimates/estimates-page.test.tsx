import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { renderWithProviders } from "@/test/render";
import { apiUrl, http, HttpResponse, server } from "@/test/server";
import { EstimatesPage } from "./estimates-page";

const est = {
  id: "e1",
  request_id: "r14",
  request: { id: "r14", display_id: "REQ-14", title: "Chiller noise in the server room" },
  version: 1,
  status: "AWAITING_APPROVAL",
  total_minor: 494000,
  currency: "KGS",
  created_at: "2026-11-15T03:02:00Z",
};

describe("EstimatesPage", () => {
  it("shows the REQ id and title from the API item and links to the request (no /requests lookup)", async () => {
    let requestsCalled = false;
    server.use(
      http.get(apiUrl("/estimates"), () => HttpResponse.json({ items: [est], total: 1, page: 1, page_size: 20 })),
      http.get(apiUrl("/requests"), () => ((requestsCalled = true), HttpResponse.json({ items: [], total: 0, page: 1, page_size: 100 }))),
    );
    renderWithProviders(<EstimatesPage />, { route: "/estimates" });
    const link = await screen.findByRole("link", { name: /REQ-14/ });
    expect(link).toHaveAttribute("href", "/requests/r14");
    expect(link).toHaveTextContent("Chiller noise in the server room");
    const table = within(screen.getByRole("table"));
    expect(table.getByText("Awaiting approval")).toBeInTheDocument();
    expect(table.queryByText(/Awaiting_approval/)).not.toBeInTheDocument();
    expect(requestsCalled).toBe(false);
  });
});
