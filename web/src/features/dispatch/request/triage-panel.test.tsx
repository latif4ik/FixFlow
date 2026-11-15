import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { renderWithProviders } from "@/test/render";
import { apiUrl, http, HttpResponse, server } from "@/test/server";
import { CATEGORY_HVAC, makeCtx } from "../fixtures";
import { TriagePanel } from "./triage-panel";

function categories() {
  server.use(
    http.get(apiUrl("/categories"), () =>
      HttpResponse.json({ items: [CATEGORY_HVAC, { ...CATEGORY_HVAC, id: "cat-el", name: "Electrical" }], total: 2, page: 1, page_size: 100 }),
    ),
  );
}

describe("TriagePanel", () => {
  it("marks a submitted request as triaged with an optional internal note", async () => {
    categories();
    let body: unknown = null;
    server.use(
      http.post(apiUrl("/requests/r1/triage"), async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({});
      }),
    );
    renderWithProviders(<TriagePanel ctx={makeCtx({ status: "SUBMITTED", allowed_actions: ["triage", "cancel", "add_note", "edit_priority_category", "link_duplicate"] })} />);
    const form = screen.getByRole("form", { name: "Mark triaged" });
    await userEvent.type(within(form).getByLabelText(/Triage note/), "Needs HVAC tech");
    await userEvent.click(within(form).getByRole("button", { name: "Mark triaged" }));
    await waitFor(() => expect(body).toEqual({ note: "Needs HVAC tech" }));
  });

  it("explains why triage is unavailable once the request is triaged", () => {
    categories();
    renderWithProviders(<TriagePanel ctx={makeCtx()} />);
    expect(screen.queryByRole("form", { name: "Mark triaged" })).not.toBeInTheDocument();
    expect(screen.getByText(/Triage is only available while a request is Submitted/)).toBeInTheDocument();
  });

  it("shows the request's current category after the list loads, even when it is not the first option", async () => {
    server.use(
      http.get(apiUrl("/categories"), () =>
        HttpResponse.json({ items: [{ ...CATEGORY_HVAC, id: "cat-el", name: "Electrical" }, CATEGORY_HVAC], total: 2, page: 1, page_size: 100 }),
      ),
    );
    renderWithProviders(<TriagePanel ctx={makeCtx()} />);
    const form = screen.getByRole("form", { name: "Change category or priority" });
    await screen.findByRole("option", { name: "Electrical" });
    const select = within(form).getByLabelText("Category") as HTMLSelectElement;
    expect(select.value).toBe(CATEGORY_HVAC.id);
    expect(select.selectedOptions[0]?.textContent).toBe(CATEGORY_HVAC.name);
  });

  it("requires a reason to change category/priority and PATCHes only the changed fields", async () => {
    categories();
    let body: unknown = null;
    server.use(
      http.patch(apiUrl("/requests/r1"), async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({});
      }),
    );
    renderWithProviders(<TriagePanel ctx={makeCtx()} />);
    const form = screen.getByRole("form", { name: "Change category or priority" });
    await screen.findByRole("option", { name: "Electrical" });
    await userEvent.selectOptions(within(form).getByLabelText("Priority"), "LOW");
    await userEvent.click(within(form).getByRole("button", { name: "Save change" }));
    expect(await within(form).findByText(/Enter a reason of at least 5 characters/)).toBeInTheDocument();
    expect(body).toBeNull();
    await userEvent.type(within(form).getByLabelText(/Reason for the change/), "Tenant says it can wait");
    await userEvent.click(within(form).getByRole("button", { name: "Save change" }));
    await waitFor(() => expect(body).toEqual({ priority: "LOW", reason: "Tenant says it can wait" }));
  });

  it("finds an original request by REQ id and links the duplicate with a reason", async () => {
    categories();
    let body: unknown = null;
    server.use(
      http.get(apiUrl("/requests"), ({ request }) => {
        expect(new URL(request.url).searchParams.get("q")).toBe("REQ-12");
        const mk = (id: string, n: number) => ({ id, display_id: `REQ-${n}`, title: `Title ${n}` });
        return HttpResponse.json({ items: [mk("r1", 14), mk("r12", 12)], total: 2, page: 1, page_size: 5 });
      }),
      http.post(apiUrl("/requests/r1/duplicate"), async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({});
      }),
    );
    renderWithProviders(<TriagePanel ctx={makeCtx()} />);
    await userEvent.type(screen.getByLabelText(/Original request/), "REQ-12");
    await userEvent.click(screen.getByRole("button", { name: "Search requests" }));
    // the request itself is never offered as its own original
    const match = await screen.findByRole("button", { name: /REQ-12/ });
    expect(screen.queryByRole("button", { name: /REQ-14/ })).not.toBeInTheDocument();
    await userEvent.click(match);
    await userEvent.type(screen.getByLabelText(/Why is this a duplicate of REQ-12/), "Same chiller fault");
    await userEvent.click(screen.getByRole("button", { name: /Link as duplicate of REQ-12/ }));
    await waitFor(() => expect(body).toEqual({ duplicate_of_id: "r12", reason: "Same chiller fault" }));
  });
});
