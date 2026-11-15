import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { useAuth } from "@/lib/auth";
import { fakeSession, ORG_A, renderWithProviders } from "@/test/render";
import { apiUrl, http, HttpResponse, server } from "@/test/server";
import { OrganizationPage } from "./organization-page";

function Tz() {
  return <p data-testid="tz">{useAuth().timezone}</p>;
}

describe("organization settings", () => {
  it("updates the session timezone and refetches org-scoped data after saving", async () => {
    let tz = "Asia/Bishkek";
    let orgFetches = 0;
    server.use(
      http.get(apiUrl("/org"), () => {
        orgFetches += 1;
        return HttpResponse.json({ id: ORG_A.id, name: "Northwind", slug: "northwind", timezone: tz });
      }),
      http.patch(apiUrl("/org"), async ({ request }) => {
        const b = (await request.json()) as { timezone: string };
        tz = b.timezone;
        return HttpResponse.json({ id: ORG_A.id, name: "Northwind", slug: "northwind", timezone: tz });
      }),
    );
    renderWithProviders(
      <>
        <Tz />
        <OrganizationPage />
      </>,
      { session: fakeSession({ role: "ADMIN" }) },
    );
    const select = await screen.findByLabelText(/Time zone/);
    expect(screen.getByTestId("tz")).toHaveTextContent("Asia/Bishkek");
    await userEvent.selectOptions(select, "Europe/Berlin");
    const before = orgFetches;
    await userEvent.click(screen.getByRole("button", { name: "Save settings" }));
    await waitFor(() => expect(screen.getByTestId("tz")).toHaveTextContent("Europe/Berlin"));
    expect(JSON.parse(window.sessionStorage.getItem("fixflow.session")!).memberships[0].organization.timezone).toBe("Europe/Berlin");
    await waitFor(() => expect(orgFetches).toBeGreaterThan(before));
  });
});
