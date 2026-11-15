import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { renderWithProviders } from "@/test/render";
import { apiUrl, http, HttpResponse, server } from "@/test/server";
import { makeCtx } from "../fixtures";
import { EstimatePanel, minorToKgsInput, parseKgsToMinor } from "./estimate-panel";

const draft = {
  id: "e1",
  request_id: "r1",
  version: 1,
  status: "DRAFT",
  supersedes_id: null,
  labor_minutes: 90,
  labor_rate_minor: 60000,
  labor_cost_minor: 90000,
  materials_total_minor: 24500,
  total_minor: 114500,
  currency: "KGS",
  notes: null,
  lines: [{ id: "l1", position: 1, description: "Tap cartridge", inventory_item_id: null, quantity: "1.000", unit_price_minor: 24500, line_total_minor: 24500 }],
  created_at: "2026-11-15T00:00:00Z",
  submitted_at: null,
  decided_at: null,
};

function handlers(estimates: unknown[]) {
  server.use(
    http.get(apiUrl("/requests/r1/estimates"), () => HttpResponse.json(estimates)),
    http.get(apiUrl("/inventory"), () =>
      HttpResponse.json({ items: [{ id: "inv1", code: "FILTER", name: "Air filter", unit: "pcs", stock_quantity: "5", unit_price_minor: 12000, is_active: true }], total: 1, page: 1, page_size: 100 }),
    ),
  );
}

describe("money helpers", () => {
  it("converts KGS input to integer tyiyn and rejects negatives / junk", () => {
    expect(parseKgsToMinor("600")).toBe(60000);
    expect(parseKgsToMinor("600.5")).toBe(60050);
    expect(parseKgsToMinor("19.99")).toBe(1999);
    expect(parseKgsToMinor("-5")).toBeNull();
    expect(parseKgsToMinor("1.234")).toBeNull();
    expect(parseKgsToMinor("abc")).toBeNull();
    expect(minorToKgsInput(60000)).toBe("600");
    expect(minorToKgsInput(24550)).toBe("245.50");
  });
});

describe("EstimatePanel editor", () => {
  it("rejects negative labor/price and zero quantity without calling the API", async () => {
    handlers([]);
    let posted = false;
    server.use(http.post(apiUrl("/requests/r1/estimates"), () => ((posted = true), HttpResponse.json(draft, { status: 201 }))));
    renderWithProviders(<EstimatePanel ctx={makeCtx()} />);
    const form = await screen.findByRole("form", { name: "Estimate editor" });
    await userEvent.click(within(form).getByRole("button", { name: /Add material/ }));
    const labor = within(form).getByLabelText(/Labor minutes/);
    await userEvent.clear(labor);
    await userEvent.type(labor, "-5");
    const rate = within(form).getByLabelText(/Rate/);
    await userEvent.clear(rate);
    await userEvent.type(rate, "-1");
    await userEvent.type(within(form).getByLabelText(/^Description/), "Filter");
    const qty = within(form).getByLabelText(/Quantity/);
    await userEvent.clear(qty);
    await userEvent.type(qty, "0");
    const price = within(form).getByLabelText(/Unit price/);
    await userEvent.clear(price);
    await userEvent.type(price, "-3");
    await userEvent.click(within(form).getByRole("button", { name: "Save draft" }));
    expect(await within(form).findByText("Enter whole minutes, 0 or more")).toBeInTheDocument();
    expect(within(form).getByText(/Enter an hourly rate of 0 or more/)).toBeInTheDocument();
    expect(within(form).getByText(/Quantity must be greater than 0/)).toBeInTheDocument();
    expect(within(form).getByText("Enter a unit price of 0 or more")).toBeInTheDocument();
    expect(labor).toHaveAttribute("aria-invalid", "true");
    expect(posted).toBe(false);
  });

  it("creates a draft with rate converted to tyiyn and an inventory item defaulting the unit price", async () => {
    handlers([]);
    let body: Record<string, unknown> | null = null;
    server.use(
      http.post(apiUrl("/requests/r1/estimates"), async ({ request }) => {
        expect(request.headers.get("Idempotency-Key")).toBeTruthy();
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(draft, { status: 201 });
      }),
    );
    renderWithProviders(<EstimatePanel ctx={makeCtx()} />);
    const form = await screen.findByRole("form", { name: "Estimate editor" });
    await userEvent.click(within(form).getByRole("button", { name: /Add material/ }));
    await screen.findByRole("option", { name: "Air filter (pcs)" });
    await userEvent.selectOptions(within(form).getByLabelText(/Inventory item for line 1/), "inv1");
    expect(within(form).getByLabelText(/Unit price/)).toHaveValue("120");
    expect(within(form).getByLabelText(/^Description/)).toHaveValue("Air filter");
    const qty = within(form).getByLabelText(/Quantity/);
    await userEvent.clear(qty);
    await userEvent.type(qty, "2");
    expect(within(form).getByText(/Line total \(preview\): 240\.00 KGS/)).toBeInTheDocument();
    await userEvent.click(within(form).getByRole("button", { name: "Save draft" }));
    await waitFor(() => expect(body).not.toBeNull());
    expect(body).toEqual({
      labor_minutes: 60,
      labor_rate_minor: 60000,
      notes: null,
      lines: [{ description: "Air filter", inventory_item_id: "inv1", quantity: "2", unit_price_minor: 12000 }],
    });
  });

  it("submit asks for confirmation, then saves (PATCH + PUT lines) and submits", async () => {
    handlers([draft]);
    const calls: string[] = [];
    server.use(
      http.patch(apiUrl("/estimates/e1"), async ({ request }) => {
        calls.push(`PATCH ${JSON.stringify(await request.json())}`);
        return HttpResponse.json(draft);
      }),
      http.put(apiUrl("/estimates/e1/lines"), async ({ request }) => {
        calls.push(`PUT ${JSON.stringify(await request.json())}`);
        return HttpResponse.json(draft);
      }),
      http.post(apiUrl("/estimates/e1/submit"), ({ request }) => {
        calls.push(`SUBMIT key=${Boolean(request.headers.get("Idempotency-Key"))}`);
        return HttpResponse.json({ ...draft, status: "AWAITING_APPROVAL" });
      }),
    );
    renderWithProviders(<EstimatePanel ctx={makeCtx()} />);
    const form = await screen.findByRole("form", { name: "Estimate editor" });
    expect(within(form).getByLabelText("Server totals")).toHaveTextContent("1 145.00 KGS");
    expect(screen.getAllByText(/not revenue/).length).toBeGreaterThan(0);
    await userEvent.click(within(form).getByRole("button", { name: /Submit for approval/ }));
    const dialog = await screen.findByRole("alertdialog");
    expect(dialog).toHaveTextContent("the SLA clock pauses");
    expect(calls).toEqual([]);
    await userEvent.click(within(dialog).getByRole("button", { name: "Submit for approval" }));
    await waitFor(() => expect(calls).toHaveLength(3));
    expect(calls[0]).toBe('PATCH {"labor_minutes":90,"labor_rate_minor":60000,"notes":null}');
    expect(calls[1]).toContain('PUT {"lines":[{"description":"Tap cartridge","inventory_item_id":null,"quantity":"1","unit_price_minor":24500}]}');
    expect(calls[2]).toBe("SUBMIT key=true");
  });

  it("is read-only once submitted and offers a revision with a required explanation", async () => {
    handlers([{ ...draft, status: "AWAITING_APPROVAL", submitted_at: "2026-11-15T01:00:00Z" }]);
    let body: Record<string, unknown> | null = null;
    server.use(
      http.post(apiUrl("/requests/r1/estimates"), async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ ...draft, version: 2 }, { status: 201 });
      }),
    );
    renderWithProviders(<EstimatePanel ctx={makeCtx({ status: "SCHEDULED" })} />);
    expect(await screen.findByText("Awaiting approval")).toBeInTheDocument();
    expect(screen.queryByRole("form", { name: "Estimate editor" })).not.toBeInTheDocument();
    expect(screen.getByText("1 145.00 KGS")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Create revision/ }));
    const dlg = await screen.findByRole("dialog");
    await userEvent.click(within(dlg).getByRole("button", { name: "Create revision" }));
    expect(await within(dlg).findByText(/Explain what changed/)).toBeInTheDocument();
    expect(body).toBeNull();
    await userEvent.type(within(dlg).getByLabelText(/Explanation/), "Extra part needed");
    await userEvent.click(within(dlg).getByRole("button", { name: "Create revision" }));
    await waitFor(() => expect(body).not.toBeNull());
    expect(body!.notes).toBe("Extra part needed");
    expect(body!.labor_rate_minor).toBe(60000);
  });
});
