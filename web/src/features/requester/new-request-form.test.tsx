import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { mockRouter } from "@/test/navigation-mock";
import { fakeSession, renderWithProviders } from "@/test/render";
import { apiUrl, errorResponse, http, HttpResponse, server } from "@/test/server";
import { NewRequestForm } from "./new-request-form";
import { zonedToUtcIso } from "./org-time";

const prop = { id: "11111111-aaaa-4aaa-8aaa-111111111111", name: "Northwind HQ Tower", address: "x", contact_instructions: null, is_active: true };
const cat = { id: "22222222-aaaa-4aaa-8aaa-222222222222", name: "Plumbing", description: null, default_duration_minutes: 60, is_enabled: true, required_skills: [] };
const asset = { id: "33333333-aaaa-4aaa-8aaa-333333333333", property_id: prop.id, code: "AC-1", name: "Rooftop AC", asset_type: "HVAC", serial_number: null, installed_on: null, status: "ACTIVE", notes: null };
const retired = { ...asset, id: "44444444-aaaa-4aaa-8aaa-444444444444", code: "OLD-1", name: "Old unit", status: "RETIRED" };
const page = (items: unknown[]) => HttpResponse.json({ items, total: items.length, page: 1, page_size: 100 });

function setup(overrides: { properties?: unknown[] } = {}) {
  server.use(
    http.get(apiUrl("/properties"), () => page(overrides.properties ?? [prop])),
    http.get(apiUrl("/categories"), () => page([cat])),
    http.get(apiUrl("/assets"), () => page([asset, retired])),
  );
  return renderWithProviders(<NewRequestForm />, { session: fakeSession({ role: "REQUESTER" }), route: "/requests/new" });
}

async function fillValid() {
  await userEvent.type(await screen.findByLabelText(/^Title/), "Leaking tap in the kitchen");
  await userEvent.type(screen.getByLabelText(/^Description/), "The tap in the staff kitchen drips constantly since Monday.");
  await userEvent.selectOptions(screen.getByLabelText(/^Category/), cat.id);
  await userEvent.selectOptions(screen.getByLabelText(/^Property/), prop.id);
}

describe("New request form", () => {
  it("shows required-field validation messages and sends nothing (QA-02)", async () => {
    let posted = false;
    server.use(
      http.post(apiUrl("/requests"), () => {
        posted = true;
        return HttpResponse.json({}, { status: 201 });
      }),
    );
    setup();
    await userEvent.type(await screen.findByLabelText(/^Title/), "abc");
    await userEvent.type(screen.getByLabelText(/^Description/), "too short");
    await userEvent.click(screen.getByRole("button", { name: "Submit request" }));
    expect(await screen.findByText("Title must be at least 5 characters.")).toBeInTheDocument();
    expect(screen.getByText("Description must be at least 20 characters.")).toBeInTheDocument();
    expect(screen.getByText("Choose a category.")).toBeInTheDocument();
    expect(screen.getByText("Choose a property.")).toBeInTheDocument();
    expect(posted).toBe(false);
  });

  it("validates the preferred window (end after start)", async () => {
    setup();
    await fillValid();
    await userEvent.type(screen.getByLabelText("Date"), "2026-12-01");
    await userEvent.type(screen.getByLabelText("From"), "10:00");
    await userEvent.type(screen.getByLabelText("To"), "09:00");
    await userEvent.click(screen.getByRole("button", { name: "Submit request" }));
    expect(await screen.findByText("End time must be after the start time.")).toBeInTheDocument();
  });

  it("shows a server 422 on the matching field", async () => {
    server.use(
      http.post(apiUrl("/requests"), () => errorResponse(422, "validation_error", "Request validation failed.", [{ field: "body.title", message: "Title is already used by an open request." }])),
    );
    setup();
    await fillValid();
    await userEvent.click(screen.getByRole("button", { name: "Submit request" }));
    const field = await screen.findByLabelText(/^Title/);
    const err = await screen.findByText("Title is already used by an open request.");
    expect(field).toHaveAttribute("aria-invalid", "true");
    expect(field.getAttribute("aria-describedby")).toContain(err.id);
  });

  it("lists only non-retired assets of the chosen property and creates the request with an Idempotency-Key", async () => {
    let body: Record<string, unknown> | null = null;
    let key: string | null = null;
    server.use(
      http.post(apiUrl("/requests"), async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        key = request.headers.get("idempotency-key");
        return HttpResponse.json({ id: "new-1", display_id: "REQ-99" }, { status: 201 });
      }),
    );
    setup();
    await fillValid();
    const assetSelect = screen.getByLabelText(/^Asset/);
    await waitFor(() => expect(within(assetSelect).getByRole("option", { name: "AC-1 - Rooftop AC" })).toBeInTheDocument());
    expect(within(assetSelect).queryByRole("option", { name: /OLD-1/ })).not.toBeInTheDocument();
    await userEvent.selectOptions(assetSelect, asset.id);
    await userEvent.click(screen.getByRole("radio", { name: /High/ }));
    await userEvent.click(screen.getByRole("button", { name: "Submit request" }));
    await waitFor(() => expect(mockRouter.push).toHaveBeenCalledWith("/requests/new-1"));
    expect(body).toMatchObject({ title: "Leaking tap in the kitchen", category_id: cat.id, property_id: prop.id, asset_id: asset.id, priority: "HIGH", preferred_window_start: null });
    expect(key).toBeTruthy();
  });

  it("uploads intake images after creation, keeps the request and offers retry when one fails", async () => {
    let attempts = 0;
    const forms: FormData[] = [];
    server.use(
      http.post(apiUrl("/requests"), () => HttpResponse.json({ id: "new-2", display_id: "REQ-100" }, { status: 201 })),
      http.post(apiUrl("/requests/new-2/files"), async ({ request }) => {
        forms.push(await request.formData());
        attempts++;
        return attempts === 1 ? errorResponse(500, "internal", "Disk full") : HttpResponse.json({ id: "f1" }, { status: 201 });
      }),
    );
    setup();
    await fillValid();
    const png = new File(["x"], "leak.png", { type: "image/png" });
    await userEvent.upload(screen.getByLabelText("Choose photo files"), png);
    await userEvent.click(screen.getByRole("button", { name: "Submit request" }));
    expect(await screen.findByRole("button", { name: /Retry upload of leak.png/ })).toBeInTheDocument();
    expect(mockRouter.push).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: /Retry upload of leak.png/ }));
    await waitFor(() => expect(mockRouter.push).toHaveBeenCalledWith("/requests/new-2"));
    expect(forms[0]!.get("purpose")).toBe("INTAKE");
    expect(forms[0]!.get("client_index")).toBe("0");
    expect(forms[1]!.get("client_command_id")).toBe(forms[0]!.get("client_command_id"));
  });

  it("rejects wrong image types and oversize files client-side", async () => {
    setup();
    await screen.findByLabelText(/^Title/);
    const input = screen.getByLabelText("Choose photo files");
    await userEvent.upload(input, new File(["x"], "doc.pdf", { type: "application/pdf" }), { applyAccept: false });
    expect(await screen.findByText(/doc.pdf: only JPEG, PNG or WebP/)).toBeInTheDocument();
    const big = new File(["x"], "big.jpg", { type: "image/jpeg" });
    Object.defineProperty(big, "size", { value: 11 * 1024 * 1024 });
    await userEvent.upload(input, big);
    expect(await screen.findByText(/big.jpg: larger than 10 MB/)).toBeInTheDocument();
  });

  it("explains how to get access when no property is granted", async () => {
    setup({ properties: [] });
    expect(await screen.findByText("No properties available to you")).toBeInTheDocument();
    expect(screen.getByText(/Ask your organization/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Submit request" })).not.toBeInTheDocument();
  });

  it("converts the preferred window from the ORG timezone to UTC", () => {
    expect(zonedToUtcIso("2026-12-01", "09:30", "Asia/Bishkek")).toBe("2026-12-01T03:30:00.000Z");
    expect(zonedToUtcIso("2026-07-01", "00:15", "America/New_York")).toBe("2026-07-01T04:15:00.000Z");
  });
});
