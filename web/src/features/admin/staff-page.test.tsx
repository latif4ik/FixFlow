import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { fakeSession, renderWithProviders } from "@/test/render";
import { apiUrl, errorResponse, http, HttpResponse, server } from "@/test/server";
import { StaffPage } from "./staff-page";

const member = (id: string, name: string, role: string, active = true) => ({ membership_id: id, user_id: `u-${id}`, email: `${id}@x.demo`, full_name: name, phone: null, role, is_active: active, created_at: "2026-11-01T00:00:00Z" });

describe("staff page", () => {
  it("changes a role with PATCH and refreshes the list", async () => {
    let role = "TECHNICIAN";
    const patches: unknown[] = [];
    const lists: URL[] = [];
    server.use(
      http.get(apiUrl("/org/members"), ({ request }) => {
        lists.push(new URL(request.url));
        return HttpResponse.json({ items: [member("m1", "Tom Tech", role)], total: 1, page: 1, page_size: 20 });
      }),
      http.patch(apiUrl("/org/members/m1"), async ({ request }) => {
        const body = (await request.json()) as { role: string };
        patches.push(body);
        role = body.role;
        return HttpResponse.json(member("m1", "Tom Tech", role));
      }),
    );
    renderWithProviders(<StaffPage />, { session: fakeSession({ role: "ADMIN" }) });
    const user = userEvent.setup();
    const select = await screen.findByLabelText("Role for Tom Tech");
    await user.selectOptions(select, "DISPATCHER");
    await waitFor(() => expect(patches).toEqual([{ role: "DISPATCHER" }]));
    await waitFor(() => expect(lists.length).toBeGreaterThanOrEqual(2)); // list invalidated and refetched
    await waitFor(() => expect(screen.getByLabelText("Role for Tom Tech")).toHaveValue("DISPATCHER"));
  });

  it("confirms before deactivating and shows the server's 409 message", async () => {
    let patched = 0;
    server.use(
      http.get(apiUrl("/org/members"), () => HttpResponse.json({ items: [member("m1", "Ada Admin", "ADMIN")], total: 1, page: 1, page_size: 20 })),
      http.patch(apiUrl("/org/members/m1"), () => {
        patched += 1;
        return errorResponse(409, "conflict", "You cannot deactivate the last active administrator.");
      }),
    );
    renderWithProviders(<StaffPage />, { session: fakeSession({ role: "ADMIN" }) });
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Deactivate Ada Admin" }));
    const dialog = await screen.findByRole("alertdialog");
    expect(within(dialog).getByText(/Deactivate Ada Admin\?/)).toBeInTheDocument();
    expect(patched).toBe(0); // nothing happens until confirmed
    await user.click(within(dialog).getByRole("button", { name: "Deactivate" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("You cannot deactivate the last active administrator.");
    expect(patched).toBe(1);
  });

  it("validates the add-member form inline", async () => {
    server.use(http.get(apiUrl("/org/members"), () => HttpResponse.json({ items: [], total: 0, page: 1, page_size: 20 })));
    renderWithProviders(<StaffPage />, { session: fakeSession({ role: "ADMIN" }) });
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: /Add member/ }));
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Add member" }));
    expect(await screen.findByText("Enter a valid email address.")).toBeInTheDocument();
    expect(screen.getByText("Enter the full name.")).toBeInTheDocument();
  });
});
