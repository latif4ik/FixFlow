import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { renderWithProviders } from "@/test/render";
import { apiUrl, http, HttpResponse, server } from "@/test/server";
import { AccessPanel } from "./property-detail";

const grant = (id: string, name: string) => ({ membership_id: id, full_name: name, email: `${id}@x.demo`, granted_by_membership_id: "g", created_at: "2026-11-14T10:00:00Z" });
const member = (id: string, name: string) => ({ membership_id: id, user_id: `u-${id}`, email: `${id}@x.demo`, full_name: name, role: "REQUESTER", is_active: true, created_at: "2026-11-14T10:00:00Z" });

describe("AccessPanel", () => {
  it("grants access to a requester who is not yet listed, then refreshes the list", async () => {
    let grants = [grant("m1", "Requester One")];
    let body: unknown = null;
    server.use(
      http.get(apiUrl("/properties/p1/access"), () => HttpResponse.json({ items: grants, total: grants.length, page: 1, page_size: 100 })),
      http.get(apiUrl("/org/members"), ({ request }) => {
        expect(new URL(request.url).searchParams.get("role")).toBe("REQUESTER");
        return HttpResponse.json({ items: [member("m1", "Requester One"), member("m2", "Requester Two")], total: 2, page: 1, page_size: 100 });
      }),
      http.post(apiUrl("/properties/p1/access"), async ({ request }) => {
        expect(request.headers.get("Idempotency-Key")).toBeTruthy();
        body = await request.json();
        grants = [...grants, grant("m2", "Requester Two")];
        return HttpResponse.json(grants[1], { status: 201 });
      }),
    );
    renderWithProviders(<AccessPanel propertyId="p1" />);
    const list = await screen.findByRole("list", { name: "Requesters with access" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(1);
    const select = screen.getByLabelText("Grant access to a requester");
    // already granted requesters are not offered
    await screen.findByRole("option", { name: /Requester Two/ });
    expect(screen.queryByRole("option", { name: /Requester One/ })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Grant access" })).toBeDisabled();
    await userEvent.selectOptions(select, "m2");
    await userEvent.click(screen.getByRole("button", { name: "Grant access" }));
    await waitFor(() => expect(body).toEqual({ membership_id: "m2" }));
    await waitFor(() => expect(within(screen.getByRole("list", { name: "Requesters with access" })).getAllByRole("listitem")).toHaveLength(2));
  });

  it("revokes only after confirmation", async () => {
    let grants = [grant("m1", "Requester One")];
    let deleted: string | null = null;
    server.use(
      http.get(apiUrl("/properties/p1/access"), () => HttpResponse.json({ items: grants, total: grants.length, page: 1, page_size: 100 })),
      http.get(apiUrl("/org/members"), () => HttpResponse.json({ items: [], total: 0, page: 1, page_size: 100 })),
      http.delete(apiUrl("/properties/p1/access/:mid"), ({ params }) => {
        deleted = String(params.mid);
        grants = [];
        return new HttpResponse(null, { status: 204 });
      }),
    );
    renderWithProviders(<AccessPanel propertyId="p1" />);
    await userEvent.click(await screen.findByRole("button", { name: "Revoke access for Requester One" }));
    const dialog = await screen.findByRole("alertdialog");
    expect(deleted).toBeNull();
    await userEvent.click(within(dialog).getByRole("button", { name: "Keep access" }));
    expect(deleted).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Revoke access for Requester One" }));
    await userEvent.click(within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Revoke access" }));
    await waitFor(() => expect(deleted).toBe("m1"));
    expect(await screen.findByText("No requester has access to this property yet.")).toBeInTheDocument();
  });
});
