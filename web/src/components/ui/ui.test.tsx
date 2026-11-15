import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { renderWithProviders } from "@/test/render";
import { apiUrl, http, HttpResponse, server } from "@/test/server";
import { AuthImage, ConfirmDialog, DataTable, Money, PriorityBadge, SlaBadge, StatusBadge } from "./index";
import { REQUEST_STATUSES } from "@/lib/api/types";

describe("badges", () => {
  it("every status has an icon and a text label (never color only)", () => {
    for (const s of REQUEST_STATUSES) {
      const { container, unmount } = render(<StatusBadge status={s} />);
      expect(container.querySelector("svg")).not.toBeNull();
      expect(container.textContent?.trim().length).toBeGreaterThan(2);
      unmount();
    }
  });
  it("renders SLA text per state", () => {
    renderWithProviders(
      <>
        <SlaBadge state="AT_RISK" dueAt="2026-11-15T06:32:00Z" remainingMinutes={50} />
        <SlaBadge state="OVERDUE" dueAt="2026-11-15T06:32:00Z" overdueByMinutes={12} />
        <SlaBadge state="PAUSED" />
        <PriorityBadge priority="HIGH" />
        <Money minor={120000} />
      </>,
    );
    expect(screen.getByText(/SLA at risk · due .* · 50 min left/)).toBeInTheDocument();
    expect(screen.getByText(/Overdue · due .* · 12 min late/)).toBeInTheDocument();
    expect(screen.getByText("SLA paused")).toBeInTheDocument();
    expect(screen.getByText("1 200.00 KGS")).toBeInTheDocument();
  });
});

describe("DataTable", () => {
  type Row = { id: string; name: string };
  const cols = [
    { key: "name", header: "Name", sortKey: "name", cell: (r: Row) => r.name },
  ];
  it("calls sort and page callbacks, shows empty and loading states", async () => {
    const onSort = vi.fn();
    const onPage = vi.fn();
    const { rerender } = render(
      <DataTable caption="Things" columns={cols} rows={[{ id: "1", name: "Alpha" }]} rowKey={(r) => r.id} page={1} pageSize={1} total={3} onPageChange={onPage} sort={{ key: "name", dir: "asc" }} onSortChange={onSort} />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Name" }));
    expect(onSort).toHaveBeenCalledWith({ key: "name", dir: "desc" });
    expect(screen.getByRole("columnheader", { name: "Name" })).toHaveAttribute("aria-sort", "ascending");
    await userEvent.click(screen.getByRole("button", { name: "Next page" }));
    expect(onPage).toHaveBeenCalledWith(2);
    rerender(<DataTable caption="Things" columns={cols} rows={[]} rowKey={(r) => r.id} empty={<p>No things</p>} />);
    expect(screen.getByText("No things")).toBeInTheDocument();
    rerender(<DataTable caption="Things" columns={cols} rows={undefined} loading rowKey={(r) => r.id} />);
    expect(screen.getByRole("status")).toHaveTextContent("Loading");
  });
});

describe("ConfirmDialog", () => {
  it("requires a reason of the minimum length and ignores duplicate clicks", async () => {
    const onConfirm = vi.fn(() => new Promise<void>((r) => setTimeout(r, 30)));
    const onOpenChange = vi.fn();
    render(<ConfirmDialog open onOpenChange={onOpenChange} title="Unassign?" confirmLabel="Unassign" reason={{ minLength: 5 }} onConfirm={onConfirm} />);
    const btn = screen.getByRole("button", { name: "Unassign" });
    expect(btn).toBeDisabled();
    await userEvent.type(screen.getByLabelText(/Reason/), "abc");
    expect(btn).toBeDisabled();
    await userEvent.type(screen.getByLabelText(/Reason/), "de");
    expect(btn).toBeEnabled();
    await userEvent.dblClick(btn);
    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
    expect(onConfirm).toHaveBeenCalledTimes(1);
    expect(onConfirm).toHaveBeenCalledWith("abcde");
  });
});

describe("AuthImage", () => {
  it("fetches the file with auth headers and renders an object URL, revoking it on unmount", async () => {
    let auth: string | null = null;
    server.use(
      http.get(apiUrl("/files/f1"), ({ request }) => {
        auth = request.headers.get("authorization");
        return new HttpResponse(new Uint8Array([1, 2, 3]), { headers: { "content-type": "image/png" } });
      }),
    );
    const create = vi.fn(() => "blob:test-1");
    const revoke = vi.fn();
    URL.createObjectURL = create;
    URL.revokeObjectURL = revoke;
    const { unmount } = renderWithProviders(<AuthImage fileId="f1" alt="Leak photo" />);
    const img = await screen.findByAltText("Leak photo");
    expect(img).toHaveAttribute("src", "blob:test-1");
    expect(auth).toBe("Bearer test-token");
    unmount();
    expect(revoke).toHaveBeenCalledWith("blob:test-1");
  });
});
