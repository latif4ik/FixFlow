"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Plus } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { Badge, Button, DataTable, DateTime, Dialog, ErrorState, FormField, FormServerError, Input, InlineNote, Label, Panel, PriorityBadge, Select, Skeleton, StatusBadge, Switch, Textarea } from "@/components/ui";
import type { Column } from "@/components/ui";
import type { Page, Priority, Schemas } from "@/lib/api";
import { useOrgTimezone } from "@/lib/auth";
import { qk, useApiMutation, useApiQuery } from "@/lib/query";
import { useNow } from "@/lib/use-now";
import { ymdInTz } from "@/features/dashboard/tz";
import { AdminPage } from "./shared";

type Plan = Schemas["PlanOut"];
type PlanDetail = Schemas["PlanDetail"];
type Report = Schemas["GenerationReport"];
const PRIORITIES: Priority[] = ["LOW", "NORMAL", "HIGH"];
const PAGE_SIZE = 20;

function ymdLabel(ymd: string | null | undefined) {
  return ymd ? <DateTime value={`${ymd}T12:00:00Z`} style="date" tz="UTC" /> : <span className="text-muted">-</span>;
}

/* ---------------- create ---------------- */

const planSchema = z.object({
  asset_id: z.string().min(1, "Choose an asset."),
  category_id: z.string().min(1, "Choose a category."),
  title: z.string().trim().min(3, "Enter at least 3 characters.").max(120, "At most 120 characters."),
  description: z.string().trim().min(20, "Describe the work in at least 20 characters.").max(2000, "At most 2000 characters."),
  priority: z.enum(["LOW", "NORMAL", "HIGH"]),
  first_date: z.string().min(1, "Choose the first date."),
  recurrence: z.enum(["WEEKLY", "MONTHLY"]),
});
type PlanForm = z.infer<typeof planSchema>;

function CreatePlanDialog({ onClose }: { onClose: () => void }) {
  const assets = useApiQuery<Page<Schemas["AssetOut"]>>({ queryKey: (o) => qk.assets.list(o, { status: "ACTIVE", all: true }), path: "/assets", query: { status: "ACTIVE", page_size: 100 } });
  const cats = useApiQuery<Page<Schemas["CategoryOut"]>>({ queryKey: (o) => qk.categories.list(o, { enabled: true }), path: "/categories", query: { page_size: 100 } });
  const form = useForm<PlanForm>({
    resolver: zodResolver(planSchema),
    defaultValues: { asset_id: "", category_id: "", title: "", description: "", priority: "NORMAL", first_date: "", recurrence: "MONTHLY" },
  });
  const create = useApiMutation<Plan, PlanForm>({
    request: (v) => ({ path: "/maintenance-plans", body: v }),
    idempotent: true,
    invalidate: (o) => [qk.maintenance.all(o)],
    successMessage: "Maintenance plan created.",
    form,
    onSuccess: onClose,
  });
  const err = form.formState.errors;
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()} title="New maintenance plan" description="Requests are generated automatically for each occurrence." className="max-w-xl">
      <form onSubmit={form.handleSubmit((v) => create.mutate(v))} noValidate className="flex flex-col gap-4">
        <FormField label="Asset" error={err.asset_id?.message} hint="Only active assets can have plans." required>
          <Select {...form.register("asset_id")}>
            <option value="">Choose an asset</option>
            {assets.data?.items.map((a) => (
              <option key={a.id} value={a.id}>
                {a.code} · {a.name}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField label="Category" error={err.category_id?.message} required>
          <Select {...form.register("category_id")}>
            <option value="">Choose a category</option>
            {cats.data?.items.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField label="Title" error={err.title?.message} required>
          <Input {...form.register("title")} />
        </FormField>
        <FormField label="Description" hint="At least 20 characters. Copied to each generated request." error={err.description?.message} required>
          <Textarea rows={3} {...form.register("description")} />
        </FormField>
        <div className="grid gap-4 sm:grid-cols-3">
          <FormField label="Priority" error={err.priority?.message} required>
            <Select {...form.register("priority")}>
              {PRIORITIES.map((p) => (
                <option key={p} value={p}>
                  {p.charAt(0) + p.slice(1).toLowerCase()}
                </option>
              ))}
            </Select>
          </FormField>
          <FormField label="First date" error={err.first_date?.message} required>
            <Input type="date" {...form.register("first_date")} />
          </FormField>
          <FormField label="Repeats" error={err.recurrence?.message} required>
            <Select {...form.register("recurrence")}>
              <option value="WEEKLY">Weekly</option>
              <option value="MONTHLY">Monthly</option>
            </Select>
          </FormField>
        </div>
        <FormServerError form={form} />
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={create.isPending}>
            Create plan
          </Button>
        </div>
      </form>
    </Dialog>
  );
}

/* ---------------- detail ---------------- */

function PlanDetailDialog({ id, onClose }: { id: string; onClose: () => void }) {
  const q = useApiQuery<PlanDetail>({ queryKey: (o) => qk.maintenance.detail(o, id), path: `/maintenance-plans/${id}` });
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()} title={q.data?.title ?? "Maintenance plan"} className="max-w-2xl">
      {q.error ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : !q.data ? (
        <Skeleton className="h-40 w-full" />
      ) : (
        <div className="flex flex-col gap-4 text-sm">
          <p className="text-text">{q.data.description}</p>
          <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <div>
              <dt className="text-[13px] text-muted">Asset</dt>
              <dd className="font-semibold">{q.data.asset.code}</dd>
            </div>
            <div>
              <dt className="text-[13px] text-muted">Repeats</dt>
              <dd className="font-semibold capitalize">{q.data.recurrence.toLowerCase()}</dd>
            </div>
            <div>
              <dt className="text-[13px] text-muted">Next occurrence</dt>
              <dd className="font-semibold">{q.data.is_enabled ? ymdLabel(q.data.next_occurrence) : "Plan disabled"}</dd>
            </div>
            <div>
              <dt className="text-[13px] text-muted">Generated so far</dt>
              <dd className="font-semibold">{q.data.generated_total} requests</dd>
            </div>
          </dl>
          <h3 className="font-heading text-base font-bold">Generated requests</h3>
          {q.data.generated.length === 0 ? (
            <p className="text-muted">Nothing generated yet.</p>
          ) : (
            <ul className="divide-y divide-border">
              {q.data.generated.map((g) => (
                <li key={g.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
                  <span className="flex flex-wrap items-center gap-3">
                    <Link href={`/requests/${g.id}`} className="font-semibold text-primary hover:text-primary-dark">
                      {g.display_id}
                    </Link>
                    <span className="text-muted">for {ymdLabel(g.occurrence_date)}</span>
                  </span>
                  <StatusBadge status={g.status} />
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </Dialog>
  );
}

/* ---------------- generate ---------------- */

function GeneratePanel() {
  const tz = useOrgTimezone();
  const now = useNow();
  const today = now ? ymdInTz(now, tz) : "";
  const [chosen, setChosen] = useState<string | null>(null);
  const asOf = chosen ?? today;
  const gen = useApiMutation<Report, string>({
    request: (as_of) => ({ path: "/maintenance-plans/generate", body: { as_of } }),
    idempotent: true,
    invalidate: (o) => [qk.maintenance.all(o), qk.requests.all(o), qk.dashboard.all(o)],
  });
  return (
    <Panel title="Generate requests now">
      <p className="text-[13px] text-muted">Creates the requests that are due on or before the chosen date. Running it again for the same date never creates duplicates.</p>
      <div className="mt-3 flex flex-wrap items-end gap-3">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="gen-date">As of date</Label>
          <Input id="gen-date" type="date" value={asOf} onChange={(e) => setChosen(e.target.value)} className="w-44" />
        </div>
        <Button variant="secondary" loading={gen.isPending} disabled={!asOf} onClick={() => gen.mutate(asOf)}>
          Generate now
        </Button>
      </div>
      {gen.data && (
        <div role="status" className="mt-3">
          <InlineNote tone={gen.data.errors > 0 ? "warning" : "success"}>
            {gen.data.requests_created} {gen.data.requests_created === 1 ? "request" : "requests"} created for {gen.data.as_of}; {gen.data.skipped_existing} already existed; {gen.data.plans_processed} plans processed
            {gen.data.errors > 0 ? `; ${gen.data.errors} errors` : ""}.
          </InlineNote>
        </div>
      )}
    </Panel>
  );
}

/* ---------------- page ---------------- */

export function MaintenancePage() {
  const [page, setPage] = useState(1);
  const [creating, setCreating] = useState(false);
  const [detail, setDetail] = useState<string | null>(null);
  const params = { page, page_size: PAGE_SIZE };
  const q = useApiQuery<Page<Plan>>({ queryKey: (o) => qk.maintenance.list(o, params), path: "/maintenance-plans", query: params });
  const toggle = useApiMutation<PlanDetail, { id: string; is_enabled: boolean }>({
    request: (v) => ({ method: "PATCH", path: `/maintenance-plans/${v.id}`, body: { is_enabled: v.is_enabled } }),
    invalidate: (o) => [qk.maintenance.all(o)],
    successMessage: (p) => `Plan ${p.is_enabled ? "enabled" : "disabled"}.`,
  });
  const columns: Column<Plan>[] = [
    { key: "asset", header: "Asset", cell: (p) => <span><strong className="text-ink">{p.asset.code}</strong><span className="block text-[13px] text-muted">{p.asset.name}</span></span> },
    { key: "title", header: "Plan", cell: (p) => <span><strong className="text-ink">{p.title}</strong><span className="block text-[13px] text-muted">{p.category.name}</span></span> },
    { key: "prio", header: "Priority", cell: (p) => <PriorityBadge priority={p.priority} /> },
    { key: "rec", header: "Repeats", cell: (p) => <span className="capitalize">{p.recurrence.toLowerCase()}</span> },
    { key: "first", header: "First date", cell: (p) => ymdLabel(p.first_date) },
    { key: "next", header: "Next occurrence", cell: (p) => (p.is_enabled ? ymdLabel(p.next_occurrence) : <Badge>Disabled</Badge>) },
    {
      key: "enabled",
      header: "Enabled",
      cell: (p) => <Switch aria-label={`${p.title} enabled`} checked={p.is_enabled} disabled={toggle.isPending} onCheckedChange={(v) => toggle.mutate({ id: p.id, is_enabled: v })} />,
    },
    {
      key: "actions",
      header: <span className="sr-only">Actions</span>,
      className: "text-right",
      cell: (p) => (
        <Button size="sm" variant="secondary" onClick={() => setDetail(p.id)}>
          Details <span className="sr-only">of {p.title}</span>
        </Button>
      ),
    },
  ];
  return (
    <AdminPage
      title="Maintenance plans"
      description="Recurring preventive work that creates requests automatically."
      actions={
        <Button onClick={() => setCreating(true)}>
          <Plus className="size-4" aria-hidden /> New plan
        </Button>
      }
    >
      <GeneratePanel />
      <DataTable caption="Maintenance plans" columns={columns} rows={q.data?.items} rowKey={(p) => p.id} loading={q.isLoading} error={q.error} onRetry={() => q.refetch()} page={page} pageSize={PAGE_SIZE} total={q.data?.total ?? 0} onPageChange={setPage} />
      {creating && <CreatePlanDialog onClose={() => setCreating(false)} />}
      {detail && <PlanDetailDialog key={detail} id={detail} onClose={() => setDetail(null)} />}
    </AdminPage>
  );
}
