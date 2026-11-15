import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { fakeSession, renderWithProviders } from "@/test/render";
import { apiUrl, http, HttpResponse, server } from "@/test/server";
import { InventoryPage } from "./inventory-page";

const item = (stock: string) => ({
  id: "i1",
  code: "PIPE-15",
  name: "Copper pipe 15 mm",
  unit: "m",
  stock_quantity: stock,
  reorder_threshold: "10.000",
  unit_price_minor: 12000,
  currency: "KGS",
  is_active: true,
  low_stock: Number(stock) <= 10,
});

describe("inventory page", () => {
  it("highlights low-stock rows with icon and text, and shows the low-stock list", async () => {
    server.use(
      http.get(apiUrl("/inventory/low-stock"), () => HttpResponse.json([item("4.000")])),
      http.get(apiUrl("/inventory"), () => HttpResponse.json({ items: [item("4.000")], total: 1, page: 1, page_size: 20 })),
    );
    renderWithProviders(<InventoryPage />, { session: fakeSession({ role: "ADMIN" }) });
    expect(await screen.findByText("Low stock")).toBeInTheDocument();
    expect(await screen.findByLabelText("Low-stock items")).toHaveTextContent("Copper pipe 15 mm: 4 m left");
    expect(screen.getByText("120.00 KGS")).toBeInTheDocument();
  });

  it("validates Add stock (quantity > 0, reason required), then posts and refreshes the list", async () => {
    let stock = "4.000";
    let lists = 0;
    const posts: unknown[] = [];
    server.use(
      http.get(apiUrl("/inventory/low-stock"), () => HttpResponse.json([])),
      http.get(apiUrl("/inventory"), () => {
        lists += 1;
        return HttpResponse.json({ items: [item(stock)], total: 1, page: 1, page_size: 20 });
      }),
      http.post(apiUrl("/inventory/i1/additions"), async ({ request }) => {
        posts.push(await request.json());
        stock = "24.000";
        return HttpResponse.json({ id: "mv1" }, { status: 201 });
      }),
    );
    renderWithProviders(<InventoryPage />, { session: fakeSession({ role: "ADMIN" }) });
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Add stock Copper pipe 15 mm" }));
    const dialog = await screen.findByRole("dialog");

    // empty -> both messages, nothing sent
    await user.click(within(dialog).getByRole("button", { name: "Add stock" }));
    expect(await within(dialog).findByText("Enter a quantity.")).toBeInTheDocument();
    expect(within(dialog).getByText("Enter a reason (at least 3 characters).")).toBeInTheDocument();

    // zero quantity -> must be greater than 0
    await user.type(within(dialog).getByLabelText(/Quantity received/), "0");
    await user.click(within(dialog).getByRole("button", { name: "Add stock" }));
    expect(await within(dialog).findByText("Quantity must be greater than 0.")).toBeInTheDocument();
    expect(posts).toHaveLength(0);

    const before = lists;
    await user.clear(within(dialog).getByLabelText(/Quantity received/));
    await user.type(within(dialog).getByLabelText(/Quantity received/), "20");
    await user.type(within(dialog).getByLabelText(/Reason/), "Supplier delivery");
    await user.click(within(dialog).getByRole("button", { name: "Add stock" }));
    await waitFor(() => expect(posts).toEqual([{ quantity: 20, reason: "Supplier delivery" }]));
    await waitFor(() => expect(lists).toBeGreaterThan(before)); // list refetched
    expect(await screen.findByText("24")).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
