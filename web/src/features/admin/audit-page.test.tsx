import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { fakeSession, renderWithProviders } from "@/test/render";
import { apiUrl, http, HttpResponse, server } from "@/test/server";
import { AuditPage } from "./audit-page";

const event = {
  id: "e1",
  actor_membership_id: "m1",
  actor_name: "Ada Admin",
  action: "member.role_change",
  target_type: "membership",
  target_id: "11111111-aaaa-bbbb-cccc-000000000000",
  before: { role: "TECHNICIAN" },
  after: { role: "DISPATCHER" },
  created_at: "2026-11-14T10:00:00Z",
};

describe("audit page", () => {
  it("sends filters as API params (dates converted to org-timezone instants) and expands before -> after", async () => {
    const urls: URL[] = [];
    server.use(
      http.get(apiUrl("/org/members"), () => HttpResponse.json({ items: [{ membership_id: "m1", full_name: "Ada Admin" }], total: 1, page: 1, page_size: 100 })),
      http.get(apiUrl("/audit"), ({ request }) => {
        urls.push(new URL(request.url));
        return HttpResponse.json({ items: [event], total: 1, page: 1, page_size: 20 });
      }),
    );
    renderWithProviders(<AuditPage />, { session: fakeSession({ role: "ADMIN" }) });
    const user = userEvent.setup();
    expect(await screen.findByText("member.role_change")).toBeInTheDocument();
    expect(urls[0]!.searchParams.get("action")).toBeNull();

    await user.type(screen.getByLabelText("Action"), "member.role_change");
    await user.type(screen.getByLabelText("Target type"), "membership");
    await user.selectOptions(await screen.findByRole("combobox", { name: "Actor" }), "m1");
    await user.type(screen.getByLabelText("From"), "2026-11-10");
    await user.click(screen.getByRole("button", { name: "Apply filters" }));
    await waitFor(() => expect(urls.length).toBeGreaterThan(1));
    const p = urls[urls.length - 1]!.searchParams;
    expect(p.get("action")).toBe("member.role_change");
    expect(p.get("target_type")).toBe("membership");
    expect(p.get("actor")).toBe("m1");
    expect(p.get("date_from")).toBe("2026-11-09T18:00:00.000Z"); // 10 Nov 00:00 in Asia/Bishkek (UTC+6)
    expect(p.get("page")).toBe("1");

    await user.click(screen.getByRole("button", { name: /Ada Admin/ }));
    const table = await screen.findByRole("table", { name: "Changed fields, before and after" });
    const row = within(table).getByRole("row", { name: /role/ });
    expect(row).toHaveTextContent("TECHNICIAN");
    expect(row).toHaveTextContent("DISPATCHER");
  });
});
