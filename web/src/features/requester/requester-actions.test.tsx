import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { Toaster } from "@/components/ui";
import { RequestDetailPage } from "@/features/request-detail/request-detail-page";
import { fakeSession, renderWithProviders } from "@/test/render";
import { apiUrl, errorResponse, http, HttpResponse, server } from "@/test/server";

const est = {
  id: "e1",
  request_id: "r1",
  version: 2,
  status: "AWAITING_APPROVAL",
  supersedes_id: "e0",
  labor_minutes: 90,
  labor_rate_minor: 50000,
  labor_cost_minor: 75000,
  materials_total_minor: 28400,
  total_minor: 103400,
  currency: "KGS",
  notes: "Includes the cartridge.",
  lines: [{ id: "l1", position: 1, description: "Tap cartridge", inventory_item_id: null, quantity: "1.000", unit_price_minor: 24500, line_total_minor: 24500 }],
  decided_at: null,
  decision_reason: null,
};
const prevEst = { ...est, id: "e0", version: 1, status: "REJECTED", total_minor: 150000, decided_at: "2026-11-14T10:00:00Z", decision_reason: "Too expensive" };

function detail(over: Record<string, unknown> = {}) {
  return {
    id: "r1",
    number: 1,
    display_id: "REQ-1",
    title: "Leaking tap",
    status: "ACCEPTED",
    priority: "NORMAL",
    category: { id: "c", name: "Plumbing" },
    property: { id: "p", name: "HQ", address: "1 Main" },
    asset: null,
    requester: { membership_id: "m", name: "Req" },
    created_at: "2026-11-15T03:02:00Z",
    updated_at: "2026-11-15T03:02:00Z",
    sla_state: null,
    description: "Dripping.",
    notes: [],
    files: [],
    timeline: [],
    allowed_actions: ["add_note"],
    assignment: null,
    estimate: { id: "e1", version: 2, status: "AWAITING_APPROVAL", total_minor: 103400, currency: "KGS", labor_minutes: 90, labor_cost_minor: 75000, materials_total_minor: 28400, lines: est.lines },
    materials: [],
    feedback: null,
    preferred_window_start: null,
    preferred_window_end: null,
    ...over,
  };
}

const session = () => fakeSession({ role: "REQUESTER" });

describe("Estimate decision", () => {
  it("requires a reason to reject and sends version + decision + reason", async () => {
    let body: Record<string, unknown> | null = null;
    server.use(
      http.get(apiUrl("/requests/r1"), () => HttpResponse.json(detail())),
      http.get(apiUrl("/requests/r1/estimates"), () => HttpResponse.json([prevEst, est])),
      http.post(apiUrl("/estimates/e1/decision"), async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ ...est, status: "REJECTED" });
      }),
    );
    renderWithProviders(<RequestDetailPage requestId="r1" />, { session: session() });
    expect(await screen.findByText(/not a payment or an invoice/)).toBeInTheDocument();
    expect(await screen.findByText("Note from the team: Includes the cartridge.")).toBeInTheDocument();
    expect(await screen.findByText("Earlier versions (1)")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /Reject estimate/ }));
    const dialog = await screen.findByRole("dialog", { name: "Reject this estimate?" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Reject estimate" }));
    expect(await within(dialog).findByText(/at least 5 characters/i, { selector: "p[role=alert]" })).toBeInTheDocument();
    expect(body).toBeNull();

    await userEvent.type(within(dialog).getByLabelText(/Why are you rejecting/), "Too expensive for a tap");
    await userEvent.click(within(dialog).getByRole("button", { name: "Reject estimate" }));
    await waitFor(() => expect(body).toEqual({ version: 2, decision: "REJECT", reason: "Too expensive for a tap" }));
  });

  it("approve invalidates the detail and the UI reflects the backend-driven APPROVED state", async () => {
    let approved = false;
    let body: Record<string, unknown> | null = null;
    server.use(
      http.get(apiUrl("/requests/r1"), () =>
        HttpResponse.json(approved ? detail({ estimate: { ...detail().estimate, status: "APPROVED" } }) : detail()),
      ),
      http.get(apiUrl("/requests/r1/estimates"), () => HttpResponse.json([{ ...est, status: approved ? "APPROVED" : "AWAITING_APPROVAL" }])),
      http.post(apiUrl("/estimates/e1/decision"), async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        approved = true;
        return HttpResponse.json({ ...est, status: "APPROVED" });
      }),
    );
    renderWithProviders(<RequestDetailPage requestId="r1" />, { session: session() });
    await userEvent.click(await screen.findByRole("button", { name: /Approve estimate/ }));
    await waitFor(() => expect(body).toEqual({ version: 2, decision: "APPROVE" }));
    await waitFor(() => expect(screen.queryByRole("button", { name: /Approve estimate/ })).not.toBeInTheDocument());
    expect(screen.getAllByText(/Version 2 · Approved/).length).toBeGreaterThan(0);
  });

  it("on 409 refetches the request and explains that the estimate changed", async () => {
    let detailFetches = 0;
    server.use(
      http.get(apiUrl("/requests/r1"), () => {
        detailFetches++;
        return HttpResponse.json(detail());
      }),
      http.get(apiUrl("/requests/r1/estimates"), () => HttpResponse.json([est])),
      http.post(apiUrl("/estimates/e1/decision"), () => errorResponse(409, "conflict", "Estimate version changed")),
    );
    renderWithProviders(
      <>
        <RequestDetailPage requestId="r1" />
        <Toaster />
      </>,
      { session: session() },
    );
    await userEvent.click(await screen.findByRole("button", { name: /Approve estimate/ }));
    expect(await screen.findByText("This estimate changed — review the latest version")).toBeInTheDocument();
    await waitFor(() => expect(detailFetches).toBeGreaterThanOrEqual(2));
  });
});

describe("Cancel, close, rework", () => {
  it("cancel needs confirmation and sends nothing until confirmed", async () => {
    let cancelBody: Record<string, unknown> | null = null;
    let canceled = false;
    server.use(
      http.get(apiUrl("/requests/r1"), () =>
        HttpResponse.json(canceled ? detail({ status: "CANCELED", allowed_actions: [], estimate: null }) : detail({ status: "SUBMITTED", allowed_actions: ["cancel", "edit", "add_note"], estimate: null })),
      ),
      http.post(apiUrl("/requests/r1/cancel"), async ({ request }) => {
        cancelBody = (await request.json()) as Record<string, unknown>;
        canceled = true;
        return HttpResponse.json(detail({ status: "CANCELED" }));
      }),
    );
    renderWithProviders(<RequestDetailPage requestId="r1" />, { session: session() });
    await userEvent.click(await screen.findByRole("button", { name: "Cancel request" }));
    const dialog = await screen.findByRole("dialog", { name: "Cancel this request?" });
    expect(cancelBody).toBeNull();
    await userEvent.click(within(dialog).getByRole("button", { name: "Keep request" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(cancelBody).toBeNull();

    await userEvent.click(screen.getByRole("button", { name: "Cancel request" }));
    const again = await screen.findByRole("dialog", { name: "Cancel this request?" });
    await userEvent.type(within(again).getByLabelText(/Reason/), "Fixed it myself");
    await userEvent.click(within(again).getByRole("button", { name: "Cancel request" }));
    await waitFor(() => expect(cancelBody).toEqual({ reason: "Fixed it myself" }));
    await waitFor(() => expect(screen.queryByRole("button", { name: "Cancel request" })).not.toBeInTheDocument());
  });

  it("rework requires a reason and posts to reopen", async () => {
    let body: Record<string, unknown> | null = null;
    server.use(
      http.get(apiUrl("/requests/r1"), () => HttpResponse.json(detail({ status: "COMPLETED", allowed_actions: ["close", "reopen", "add_note"], estimate: null }))),
      http.post(apiUrl("/requests/r1/reopen"), async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(detail({ status: "REOPENED" }));
      }),
    );
    renderWithProviders(<RequestDetailPage requestId="r1" />, { session: session() });
    expect(await screen.findByRole("button", { name: "Close request" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Request rework" }));
    const dialog = await screen.findByRole("dialog", { name: "Request rework" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Request rework" }));
    expect(await within(dialog).findByText(/at least 5 characters/i, { selector: "p[role=alert]" })).toBeInTheDocument();
    expect(body).toBeNull();
    await userEvent.type(within(dialog).getByLabelText(/still needs fixing/), "Still leaking underneath");
    await userEvent.click(within(dialog).getByRole("button", { name: "Request rework" }));
    await waitFor(() => expect(body).toEqual({ reason: "Still leaking underneath" }));
  });

  it("close asks for confirmation then posts", async () => {
    let closed = false;
    server.use(
      http.get(apiUrl("/requests/r1"), () => HttpResponse.json(detail({ status: "COMPLETED", allowed_actions: ["close", "reopen"], estimate: null }))),
      http.post(apiUrl("/requests/r1/close"), () => {
        closed = true;
        return HttpResponse.json(detail({ status: "CLOSED" }));
      }),
    );
    renderWithProviders(<RequestDetailPage requestId="r1" />, { session: session() });
    await userEvent.click(await screen.findByRole("button", { name: "Close request" }));
    expect(closed).toBe(false);
    const dialog = await screen.findByRole("alertdialog");
    await userEvent.click(within(dialog).getByRole("button", { name: "Close request" }));
    await waitFor(() => expect(closed).toBe(true));
  });
});

describe("Feedback", () => {
  it("requires a rating, then submits rating + comment", async () => {
    let body: Record<string, unknown> | null = null;
    server.use(
      http.get(apiUrl("/requests/r1"), () => HttpResponse.json(detail({ status: "COMPLETED", allowed_actions: ["close", "reopen"], estimate: null }))),
      http.post(apiUrl("/requests/r1/feedback"), async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ id: "f", rating: 4, comment: "Good", created_at: "2026-11-15T03:02:00Z" }, { status: 201 });
      }),
    );
    renderWithProviders(<RequestDetailPage requestId="r1" />, { session: session() });
    await userEvent.click(await screen.findByRole("button", { name: "Send feedback" }));
    expect(await screen.findByText("Choose a rating from 1 to 5.")).toBeInTheDocument();
    expect(body).toBeNull();
    await userEvent.click(screen.getByRole("radio", { name: /4 out of 5/ }));
    await userEvent.type(screen.getByLabelText(/Comment/), "Good job");
    await userEvent.click(screen.getByRole("button", { name: "Send feedback" }));
    await waitFor(() => expect(body).toEqual({ rating: 4, comment: "Good job" }));
  });

  it("is hidden once feedback exists", async () => {
    server.use(
      http.get(apiUrl("/requests/r1"), () =>
        HttpResponse.json(detail({ status: "CLOSED", allowed_actions: [], estimate: null, feedback: { id: "f", rating: 5, comment: null, created_at: "2026-11-15T03:02:00Z" } })),
      ),
    );
    renderWithProviders(<RequestDetailPage requestId="r1" />, { session: session() });
    expect(await screen.findByText("5 / 5")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Send feedback" })).not.toBeInTheDocument();
  });
});
