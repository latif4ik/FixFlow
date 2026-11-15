"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { AlertTriangle, Plus } from "lucide-react";
import { useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { z } from "zod";
import { Badge, Button, Checkbox, DataTable, DateTime, Dialog, FilterBar, FormField, FormServerError, InlineNote, Input, Label, Money, Panel, Select, Switch, Textarea } from "@/components/ui";
import type { Column } from "@/components/ui";
import type { Page, Schemas } from "@/lib/api";
import { qk, useApiMutation, useApiQuery } from "@/lib/query";
import { AdminPage, formatQty } from "./shared";

type Item = Schemas["ItemOut"];
type Movement = Schemas["MovementOut"];
const PAGE_SIZE = 20;

/* ---------------- create / edit item ---------------- */

const itemSchema = z.object({
  code: z.string().trim().min(1, "Enter a code.").max(40, "At most 40 characters."),
  name: z.string().trim().min(2, "Enter at least 2 characters.").max(120, "At most 120 characters."),
  unit: z.string().trim().min(1, "Enter a unit, for example pcs.").max(20, "At most 20 characters."),
  stock_quantity: z.number({ error: "Enter a number." }).min(0, "Stock cannot be negative."),
  reorder_threshold: z.number({ error: "Enter a number." }).min(0, "Cannot be negative."),
  price: z.number({ error: "Enter a price." }).min(0, "Price cannot be negative."),
  is_active: z.boolean(),
});
type ItemForm = z.infer<typeof itemSchema>;

function ItemDialog({ item, onClose }: { item: Item | null; onClose: () => void }) {
  const form = useForm<ItemForm>({
    resolver: zodResolver(itemSchema),
    defaultValues: {
      code: item?.code ?? "",
      name: item?.name ?? "",
      unit: item?.unit ?? "pcs",
      stock_quantity: Number(item?.stock_quantity ?? 0),
      reorder_threshold: Number(item?.reorder_threshold ?? 0),
      price: (item?.unit_price_minor ?? 0) / 100,
      is_active: item?.is_active ?? true,
    },
  });
  const save = useApiMutation<Item, ItemForm>({
    request: (v) => {
      const unit_price_minor = Math.round(v.price * 100);
      return item
        ? { method: "PATCH", path: `/inventory/${item.id}`, body: { name: v.name, unit: v.unit, reorder_threshold: v.reorder_threshold, unit_price_minor, is_active: v.is_active } }
        : { path: "/inventory", body: { code: v.code, name: v.name, unit: v.unit, stock_quantity: v.stock_quantity, reorder_threshold: v.reorder_threshold, unit_price_minor } };
    },
    idempotent: !item,
    invalidate: (o) => [qk.inventory.all(o)],
    successMessage: item ? "Item saved." : "Item created.",
    form,
    onSuccess: onClose,
  });
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()} title={item ? `Edit ${item.name}` : "New inventory item"}>
      <form onSubmit={form.handleSubmit((v) => save.mutate(v))} noValidate className="flex flex-col gap-4">
        <FormField label="Code" error={form.formState.errors.code?.message} hint={item ? "The code cannot be changed." : undefined} required>
          <Input {...form.register("code")} disabled={Boolean(item)} />
        </FormField>
        <FormField label="Name" error={form.formState.errors.name?.message} required>
          <Input {...form.register("name")} />
        </FormField>
        <div className="grid gap-4 sm:grid-cols-2">
          <FormField label="Unit" error={form.formState.errors.unit?.message} required>
            <Input {...form.register("unit")} />
          </FormField>
          <FormField label="Unit price (KGS)" error={form.formState.errors.price?.message} required>
            <Input type="number" step="0.01" min={0} {...form.register("price", { valueAsNumber: true })} />
          </FormField>
          {!item && (
            <FormField label="Initial stock" error={form.formState.errors.stock_quantity?.message} required>
              <Input type="number" step="any" min={0} {...form.register("stock_quantity", { valueAsNumber: true })} />
            </FormField>
          )}
          <FormField label="Reorder threshold" hint="At or below this, the item shows as low stock." error={form.formState.errors.reorder_threshold?.message} required>
            <Input type="number" step="any" min={0} {...form.register("reorder_threshold", { valueAsNumber: true })} />
          </FormField>
        </div>
        {item && (
          <Controller
            control={form.control}
            name="is_active"
            render={({ field }) => (
              <div className="flex items-center gap-3">
                <Switch id="item-active" checked={field.value} onCheckedChange={field.onChange} />
                <Label htmlFor="item-active">Active (can be used on requests)</Label>
              </div>
            )}
          />
        )}
        <FormServerError form={form} />
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={save.isPending}>
            {item ? "Save item" : "Create item"}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}

/* ---------------- add stock / adjust ---------------- */

const addSchema = z.object({
  amount: z.number({ error: "Enter a quantity." }).positive("Quantity must be greater than 0."),
  reason: z.string().trim().min(3, "Enter a reason (at least 3 characters).").max(300, "At most 300 characters."),
});
const adjustSchema = z.object({
  amount: z.number({ error: "Enter an amount." }).refine((n) => n !== 0, "Enter a non-zero amount (negative removes stock)."),
  reason: z.string().trim().min(3, "Enter a reason (at least 3 characters).").max(300, "At most 300 characters."),
});
type StockForm = z.infer<typeof addSchema>;

export function StockDialog({ item, mode, onClose }: { item: Item; mode: "add" | "adjust"; onClose: () => void }) {
  const form = useForm<StockForm>({ resolver: zodResolver(mode === "add" ? addSchema : adjustSchema), defaultValues: { amount: undefined, reason: "" } });
  const save = useApiMutation<unknown, StockForm>({
    request: (v) => (mode === "add" ? { path: `/inventory/${item.id}/additions`, body: { quantity: v.amount, reason: v.reason } } : { path: `/inventory/${item.id}/adjustments`, body: { delta: v.amount, reason: v.reason } }),
    idempotent: true,
    invalidate: (o) => [qk.inventory.all(o)],
    successMessage: mode === "add" ? "Stock added." : "Stock adjusted.",
    form,
    onSuccess: onClose,
  });
  return (
    <Dialog
      open
      onOpenChange={(o) => !o && onClose()}
      title={mode === "add" ? `Add stock: ${item.name}` : `Adjust stock: ${item.name}`}
      description={`Current stock: ${formatQty(item.stock_quantity)} ${item.unit}`}
    >
      <form onSubmit={form.handleSubmit((v) => save.mutate(v))} noValidate className="flex flex-col gap-4">
        <FormField
          label={mode === "add" ? `Quantity received (${item.unit})` : `Change (${item.unit})`}
          hint={mode === "add" ? "Must be greater than 0." : "Use a negative number to remove stock, for example -3."}
          error={form.formState.errors.amount?.message}
          required
        >
          <Input type="number" step="any" {...form.register("amount", { valueAsNumber: true })} />
        </FormField>
        <FormField label="Reason" error={form.formState.errors.reason?.message} required>
          <Textarea rows={3} {...form.register("reason")} />
        </FormField>
        <FormServerError form={form} />
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={save.isPending}>
            {mode === "add" ? "Add stock" : "Apply adjustment"}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}

/* ---------------- movements ---------------- */

function MovementsDialog({ item, onClose }: { item: Item; onClose: () => void }) {
  const [page, setPage] = useState(1);
  const params = { page, page_size: 10 };
  const q = useApiQuery<Page<Movement>>({ queryKey: (o) => qk.custom(o, "inventory", "detail", item.id, "movements", params), path: `/inventory/${item.id}/movements`, query: params });
  const columns: Column<Movement>[] = [
    { key: "when", header: "When", cell: (m) => <DateTime value={m.created_at} /> },
    { key: "kind", header: "Type", cell: (m) => m.kind.replace(/_/g, " ").toLowerCase() },
    { key: "delta", header: "Change", cell: (m) => <span className="tabular-nums">{Number(m.delta) > 0 ? "+" : ""}{formatQty(m.delta)} {item.unit}</span> },
    { key: "after", header: "Stock after", cell: (m) => <span className="tabular-nums">{formatQty(m.stock_after)}</span> },
    { key: "reason", header: "Reason", cell: (m) => m.reason },
    { key: "actor", header: "By", cell: (m) => m.actor?.name ?? "System" },
  ];
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()} title={`Movements: ${item.name}`} className="max-w-3xl">
      <DataTable caption={`Stock movements for ${item.name}`} columns={columns} rows={q.data?.items} rowKey={(m) => m.id} loading={q.isLoading} error={q.error} onRetry={() => q.refetch()} page={page} pageSize={10} total={q.data?.total ?? 0} onPageChange={setPage} />
    </Dialog>
  );
}

/* ---------------- page ---------------- */

export function InventoryPage() {
  const [search, setSearch] = useState("");
  const [applied, setApplied] = useState("");
  const [active, setActive] = useState("");
  const [lowOnly, setLowOnly] = useState(false);
  const [page, setPage] = useState(1);
  const [dialog, setDialog] = useState<{ kind: "edit"; item: Item | null } | { kind: "add" | "adjust" | "moves"; item: Item } | null>(null);

  const params = { q: applied || undefined, active: active === "" ? undefined : active === "true", low_stock: lowOnly || undefined, page, page_size: PAGE_SIZE };
  const q = useApiQuery<Page<Item>>({ queryKey: (o) => qk.inventory.list(o, params), path: "/inventory", query: params });
  const low = useApiQuery<Item[]>({ queryKey: (o) => qk.inventory.lowStock(o), path: "/inventory/low-stock" });

  const columns: Column<Item>[] = [
    { key: "code", header: "Code", cell: (i) => <span className="font-mono text-[13px]">{i.code}</span> },
    { key: "name", header: "Name", cell: (i) => <strong className="text-ink">{i.name}</strong> },
    { key: "unit", header: "Unit", cell: (i) => i.unit },
    {
      key: "stock",
      header: "In stock",
      cell: (i) => (
        <span className="flex flex-wrap items-center gap-2">
          <span className="tabular-nums">{formatQty(i.stock_quantity)}</span>
          {i.low_stock && (
            <Badge tone="warning" icon={AlertTriangle}>
              Low stock
            </Badge>
          )}
        </span>
      ),
    },
    { key: "threshold", header: "Reorder at", cell: (i) => <span className="tabular-nums">{formatQty(i.reorder_threshold)}</span> },
    { key: "price", header: "Unit price", cell: (i) => (i.unit_price_minor == null ? "-" : <Money minor={i.unit_price_minor} currency={i.currency ?? "KGS"} />) },
    { key: "active", header: "Status", cell: (i) => (i.is_active === false ? <Badge>Inactive</Badge> : <Badge tone="success">Active</Badge>) },
    {
      key: "actions",
      header: <span className="sr-only">Actions</span>,
      className: "text-right",
      cell: (i) => (
        <span className="flex flex-wrap justify-end gap-1.5">
          <Button size="sm" variant="secondary" onClick={() => setDialog({ kind: "add", item: i })}>
            Add stock <span className="sr-only">{i.name}</span>
          </Button>
          <Button size="sm" variant="secondary" onClick={() => setDialog({ kind: "adjust", item: i })}>
            Adjust <span className="sr-only">{i.name}</span>
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setDialog({ kind: "moves", item: i })}>
            History <span className="sr-only">of {i.name}</span>
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setDialog({ kind: "edit", item: i })}>
            Edit <span className="sr-only">{i.name}</span>
          </Button>
        </span>
      ),
    },
  ];

  return (
    <AdminPage
      title="Inventory"
      description="Parts and materials. Stock is reduced when technicians record material use on a request."
      actions={
        <Button onClick={() => setDialog({ kind: "edit", item: null })}>
          <Plus className="size-4" aria-hidden /> New item
        </Button>
      }
    >
      {low.data && low.data.length > 0 && (
        <Panel title={`Low stock (${low.data.length})`} className="border-warning">
          <ul className="flex flex-wrap gap-2" aria-label="Low-stock items">
            {low.data.map((i) => (
              <li key={i.id} className="flex items-center gap-1.5 rounded-md bg-warning-tint px-2.5 py-1.5 text-sm text-warning-dark">
                <AlertTriangle className="size-4" aria-hidden />
                <strong>{i.name}</strong>: {formatQty(i.stock_quantity)} {i.unit} left (reorder at {formatQty(i.reorder_threshold)})
              </li>
            ))}
          </ul>
        </Panel>
      )}
      {low.data && low.data.length === 0 && <InlineNote tone="success">No items are below their reorder threshold.</InlineNote>}
      <FilterBar label="Inventory filters">
        <form
          className="flex flex-col gap-1.5"
          onSubmit={(e) => {
            e.preventDefault();
            setApplied(search.trim());
            setPage(1);
          }}
        >
          <Label htmlFor="inv-q">Search</Label>
          <div className="flex gap-2">
            <Input id="inv-q" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Code or name" className="w-56" />
            <Button type="submit" variant="secondary">
              Search
            </Button>
          </div>
        </form>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="inv-active">Status</Label>
          <Select
            id="inv-active"
            value={active}
            onChange={(e) => {
              setActive(e.target.value);
              setPage(1);
            }}
            className="w-40"
          >
            <option value="">Any status</option>
            <option value="true">Active</option>
            <option value="false">Inactive</option>
          </Select>
        </div>
        <div className="flex h-10 items-center gap-2">
          <Checkbox
            id="inv-low"
            checked={lowOnly}
            onCheckedChange={(c) => {
              setLowOnly(c === true);
              setPage(1);
            }}
          />
          <Label htmlFor="inv-low">Low stock only</Label>
        </div>
      </FilterBar>
      <DataTable
        caption="Inventory items"
        columns={columns}
        rows={q.data?.items}
        rowKey={(i) => i.id}
        loading={q.isLoading}
        error={q.error}
        onRetry={() => q.refetch()}
        page={page}
        pageSize={PAGE_SIZE}
        total={q.data?.total ?? 0}
        onPageChange={setPage}
      />
      {dialog?.kind === "edit" && <ItemDialog key={dialog.item?.id ?? "new"} item={dialog.item} onClose={() => setDialog(null)} />}
      {dialog && (dialog.kind === "add" || dialog.kind === "adjust") && <StockDialog key={`${dialog.kind}-${dialog.item.id}`} item={dialog.item} mode={dialog.kind} onClose={() => setDialog(null)} />}
      {dialog?.kind === "moves" && <MovementsDialog item={dialog.item} onClose={() => setDialog(null)} />}
    </AdminPage>
  );
}
