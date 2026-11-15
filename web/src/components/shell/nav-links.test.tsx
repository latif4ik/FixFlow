import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { apiUrl, http, HttpResponse, server } from "@/test/server";
import { fakeSession, renderWithProviders } from "@/test/render";
import { NavLinks } from "./nav-links";

describe("NavLinks", () => {
  it("staff main nav has no Notifications item (the bell covers it) but the drawer does", () => {
    server.use(http.get(apiUrl("/dashboard/overdue"), () => HttpResponse.json({ count: 0, items: [], page: 1, page_size: 1 })));
    const { unmount } = renderWithProviders(<NavLinks />, { session: fakeSession({ role: "ADMIN" }) });
    expect(screen.getAllByRole("link").map((l) => l.textContent)).toEqual(["Dashboard", "Request queue", "Schedule board", "Properties and assets", "Estimates", "Overdue", "Admin"]);
    expect(screen.queryByRole("link", { name: /Notifications/ })).not.toBeInTheDocument();
    unmount();
    renderWithProviders(<NavLinks orientation="vertical" withNotifications />, { session: fakeSession({ role: "ADMIN" }) });
    expect(screen.getByRole("link", { name: /Notifications/ })).toHaveAttribute("href", "/notifications");
  });
});
