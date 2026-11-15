"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { FilePlus2, Plus, Send, Trash2, Undo2 } from "lucide-react";
import { useState } from "react";
import { useFieldArray, useForm, useWatch } from "react-hook-form";
import { z } from "zod";
import { Badge, Button, ConfirmDialog, DateTime, Dialog, FormField, FormServerError, IconButton, InlineNote, Input, LoadingState, ErrorState, Money, Panel, Select, Textarea } from "@/components/ui";
import type { Page, Schemas } from "@/lib/api/types";
import { formatDuration, formatMoney } from "@/lib/format";
import { useApiMutation, useApiQuery } from "@/lib/query/hooks";
import { qk } from "@/lib/query/keys";
import type { RequestActionProps } from "@/features/request-actions/types";

type Estimate = Schemas["EstimateOut"];
type Item = Schemas["ItemOut"];

const STATUS_META: Record<Estimate["status"], { label: string; tone: "neutral" | "warning" | "success" | "danger" | "info" }> = {
  DRAFT: { label: "Draft", tone: "neutral" },
  AWAITING_APPROVAL: { label: "Awaiting approval", tone: "warning" },
  APPROVED: { label: "Approved", tone: "success" },
  REJECTED: { label: "Rejected", tone: "danger" },
  SUPERSEDED: { label: "Superseded", tone: "neutral" },
};

/** "600" / "600.5" / "600.50" -> tyiyn (integer). null when invalid or negative. */
export function parseKgsToMinor(v: string): number | null {
  const t = v.trim().replace(",", ".");
  if (!/^\d+(\.\d{1,2})?$/.test(t)) return null;
  return Math.round(parseFloat(t) * 100);
}
export function minorToKgsInput(minor: number): string {
  return (minor / 100).toFixed(2).replace(/\.00$/, "");
}
function parseQty(v: string): number | null {
  const t = v.trim().replace(",", ".");
  if (!/^\d+(\.\d{1,3})?$/.test(t)) return null;
  const n = parseFloat(t);
  return n > 0 ? n : null;
}

export const estimateSchema = z.object({
  labor_minutes: z.string().trim().regex(/^\d+$/, "Enter whole minutes, 0 or more").refine((v) => Number(v) <= 1_000_000, "Too many minutes"),
  labor_rate: z.string().refine((v) => parseKgsToMinor(v) !== null, "Enter an hourly rate of 0 or more, e.g. 600 or 600.50"),
  notes: z.string().max(2000, "At most 2000 characters"),
  lines: z
    .array(
      z.object({
        description: z.string().trim().min(1, "Describe the material").max(300, "At most 300 characters"),
        inventory_item_id: z.string(),
        quantity: z.string().refine((v) => parseQty(v) !== null, "Quantity must be greater than 0 (up to 3 decimals)"),
        unit_price: z.string().refine((v) => parseKgsToMinor(v) !== null, "Enter a unit price of 0 or more"),
      }),
    )
    .max(100, "At most 100 lines"),
});
export type EstimateValues = z.infer<typeof estimateSchema>;

function valuesFrom(e: Estimate | undefined): EstimateValues {
  return {
    labor_minutes: String(e?.labor_minutes ?? 60),
    labor_rate: minorToKgsInput(e?.labor_rate_minor ?? 60000),
    notes: e?.notes ?? "",
    lines: (e?.lines ?? []).map((l) => ({
      description: l.description,
      inventory_item_id: l.inventory_item_id ?? "",
      quantity: String(parseFloat(l.quantity)),
      unit_price: minorToKgsInput(l.unit_price_minor),
    })),
  };
}

function bodyFrom(v: EstimateValues, notes: string | null) {
  return {
    labor_minutes: Number(v.labor_minutes),
    labor_rate_minor: parseKgsToMinor(v.labor_rate)!,
    notes: notes ?? (v.notes.trim() || null),
    lines: v.lines.map((l) => ({
      description: l.description.trim(),
      inventory_item_id: l.inventory_item_id || null,
      quantity: l.quantity.trim().replace(",", "."),
      unit_price_minor: parseKgsToMinor(l.unit_price)!,
    })),
  };
}

function ReadOnly({ e }: { e: Estimate }) {
  const m = STATUS_META[e.status];
  return (
    <div className="flex flex-col gap-3 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-semibold">Version {e.version}</span>
        <Badge tone={m.tone}>{m.label}</Badge>
        <span className="text-muted">{e.submitted_at ? <>Submitted <DateTime value={e.submitted_at} style="short" /></> : "Not submitted"}</span>
      </div>
      <dl className="grid grid-cols-[1fr_auto] gap-x-4 gap-y-1">
        <dt className="text-muted">
          Labor ({formatDuration(e.labor_minutes)} at {formatMoney(e.labor_rate_minor)}/h)
        </dt>
        <dd>
          <Money minor={e.labor_cost_minor} />
        </dd>
        {e.lines.map((l) => (
          <div key={l.id} className="contents">
            <dt className="text-muted">
              {l.description} ({parseFloat(l.quantity)} x {formatMoney(l.unit_price_minor)})
            </dt>
            <dd>
              <Money minor={l.line_total_minor} />
            </dd>
          </div>
        ))}
        <dt className="text-muted">Materials</dt>
        <dd>
          <Money minor={e.materials_total_minor} />
        </dd>
        <dt className="font-semibold">Total</dt>
        <dd className="font-semibold">
          <Money minor={e.total_minor} />
        </dd>
      </dl>
      {e.notes && <p className="text-muted">Note: {e.notes}</p>}
      {e.decision_reason && <p className="text-muted">Decision note: {e.decision_reason}</p>}
      {e.withdraw_reason && <p className="text-muted">Withdrawn: {e.withdraw_reason}</p>}
    </div>
  );
}

function Editor({ ctx, draft }: RequestActionProps & { draft: Estimate | undefined }) {
  const form = useForm<EstimateValues>({ resolver: zodResolver(estimateSchema), defaultValues: valuesFrom(draft) });
  const { fields, append, remove } = useFieldArray({ control: form.control, name: "lines" });
  const watched = useWatch({ control: form.control });
  const items = useApiQuery<Page<Item>>({ queryKey: (o) => qk.inventory.list(o, { active: true, page_size: 100 }), path: "/inventory", query: { active: true, page_size: 100 }, staleTime: 60_000 });
  const [confirm, setConfirm] = useState(false);
  const invalidate = (o: string) => [qk.requests.detail(o, ctx.requestId), qk.requests.estimates(o, ctx.requestId), qk.estimates.all(o)];

  const create = useApiMutation<Estimate, EstimateValues>({
    request: (v) => ({ path: `/requests/${ctx.requestId}/estimates`, body: bodyFrom(v, null) }),
    idempotent: true,
    invalidate,
    form,
  });
  const patch = useApiMutation<Estimate, { id: string; v: EstimateValues }>({
    request: ({ id, v }) => ({ method: "PATCH", path: `/estimates/${id}`, body: { labor_minutes: Number(v.labor_minutes), labor_rate_minor: parseKgsToMinor(v.labor_rate)!, notes: v.notes.trim() || null } }),
    form,
  });
  const putLines = useApiMutation<Estimate, { id: string; v: EstimateValues }>({
    request: ({ id, v }) => ({ method: "PUT", path: `/estimates/${id}/lines`, body: { lines: bodyFrom(v, null).lines } }),
    invalidate,
    form,
  });
  const submit = useApiMutation<Estimate, string>({
    request: (id) => ({ path: `/estimates/${id}/submit` }),
    idempotent: true,
    invalidate,
    successMessage: "Estimate submitted for approval. The SLA clock pauses until the requester decides.",
  });
  /** Persist the form: create the draft or PATCH + PUT lines. Returns the estimate id. */
  async function persist(v: EstimateValues): Promise<string | undefined> {
    if (!draft) {
      const e = await create.mutateAsync(v);
      return e?.id;
    }
    const p = await patch.mutateAsync({ id: draft.id, v });
    if (!p) return undefined;
    const l = await putLines.mutateAsync({ id: draft.id, v });
    return l?.id;
  }

  const saving = create.isPending || patch.isPending || putLines.isPending;
  const previewLines = (watched.lines ?? []).map((l) => {
    const q = parseQty(l?.quantity ?? "");
    const p = parseKgsToMinor(l?.unit_price ?? "");
    return q !== null && p !== null ? Math.round(q * p) : null;
  });
  const errs = form.formState.errors;

  return (
    <form
      aria-label="Estimate editor"
      noValidate
      className="flex flex-col gap-5"
      onSubmit={form.handleSubmit(async (v) => {
        await persist(v).then((id) => {
          if (id) form.reset(v);
        });
      })}
    >
      <FormServerError form={form} />
      <div className="grid gap-4 sm:grid-cols-2">
        <FormField label="Labor minutes" required error={errs.labor_minutes?.message}>
          <Input inputMode="numeric" {...form.register("labor_minutes")} />
        </FormField>
        <FormField label="Rate (KGS per hour)" required error={errs.labor_rate?.message}>
          <Input inputMode="decimal" {...form.register("labor_rate")} />
        </FormField>
      </div>

      <fieldset className="flex flex-col gap-3">
        <legend className="mb-1 text-sm font-semibold">Materials</legend>
        {fields.length === 0 && <p className="text-[13px] text-muted">No materials. Labor only.</p>}
        {fields.map((f, i) => (
          <div key={f.id} className="grid gap-3 rounded-lg border border-border p-3 sm:grid-cols-[1fr_96px_120px_auto]">
            <div className="flex flex-col gap-3 sm:col-span-4 sm:flex-row">
              <FormField label="Inventory item (optional)" className="sm:w-60">
                <Select
                  aria-label={`Inventory item for line ${i + 1}`}
                  {...form.register(`lines.${i}.inventory_item_id`, {
                    onChange: (e) => {
                      const item = items.data?.items.find((x) => x.id === e.target.value);
                      if (item) {
                        if (!form.getValues(`lines.${i}.description`)) form.setValue(`lines.${i}.description`, item.name);
                        if (item.unit_price_minor != null) form.setValue(`lines.${i}.unit_price`, minorToKgsInput(item.unit_price_minor));
                      }
                    },
                  })}
                >
                  <option value="">Custom material</option>
                  {items.data?.items.map((it) => (
                    <option key={it.id} value={it.id}>
                      {it.name} ({it.unit})
                    </option>
                  ))}
                </Select>
              </FormField>
            </div>
            <FormField label="Description" required error={errs.lines?.[i]?.description?.message}>
              <Input {...form.register(`lines.${i}.description`)} />
            </FormField>
            <FormField label="Quantity" required error={errs.lines?.[i]?.quantity?.message}>
              <Input inputMode="decimal" {...form.register(`lines.${i}.quantity`)} />
            </FormField>
            <FormField label="Unit price (KGS)" required error={errs.lines?.[i]?.unit_price?.message}>
              <Input inputMode="decimal" {...form.register(`lines.${i}.unit_price`)} />
            </FormField>
            <div className="flex items-end justify-between gap-2 sm:flex-col sm:items-end sm:justify-end">
              <span className="whitespace-nowrap pb-2 text-[13px] text-muted">
                Line total (preview): {previewLines[i] != null ? formatMoney(previewLines[i]!) : "-"}
              </span>
              <IconButton aria-label={`Remove material line ${i + 1}`} icon={<Trash2 className="size-4" aria-hidden />} onClick={() => remove(i)} />
            </div>
          </div>
        ))}
        <div>
          <Button variant="secondary" size="sm" onClick={() => append({ description: "", inventory_item_id: "", quantity: "1", unit_price: "0" })}>
            <Plus className="size-4" aria-hidden /> Add material
          </Button>
        </div>
      </fieldset>

      <FormField label="Note to the requester (optional)" error={errs.notes?.message}>
        <Textarea rows={2} {...form.register("notes")} />
      </FormField>

      {draft && (
        <div className="rounded-lg bg-canvas px-4 py-3 text-sm" aria-label="Server totals">
          <p className="font-semibold">
            Saved totals: <Money minor={draft.total_minor} /> <span className="font-normal text-muted">(labor <Money minor={draft.labor_cost_minor} /> + materials <Money minor={draft.materials_total_minor} />)</span>
          </p>
          <p className="mt-1 text-[13px] text-muted">The server calculates the authoritative total when you save. Unsaved edits are not included.</p>
        </div>
      )}
      <p className="text-[13px] text-muted">Amounts are an estimate, not revenue. The SLA clock pauses while the estimate awaits approval.</p>

      <div className="flex flex-wrap gap-2">
        <Button type="submit" variant="secondary" loading={saving}>
          Save draft
        </Button>
        <Button
          disabled={saving || submit.isPending}
          onClick={async () => {
            const ok = await form.trigger();
            if (ok) setConfirm(true);
          }}
        >
          <Send className="size-4" aria-hidden /> Submit for approval
        </Button>
      </div>

      <ConfirmDialog
        open={confirm}
        onOpenChange={setConfirm}
        destructive={false}
        title="Submit this estimate for approval?"
        description="The requester will be asked to approve it. The version becomes read-only and the SLA clock pauses until they decide."
        confirmLabel="Submit for approval"
        cancelLabel="Keep editing"
        onConfirm={async () => {
          const v = form.getValues();
          const id = await persist(v);
          if (!id) throw new Error("save failed");
          const done = await submit.mutateAsync(id);
          if (!done) throw new Error("submit failed");
        }}
      />
    </form>
  );
}

function NewRevision({ ctx, latest }: RequestActionProps & { latest: Estimate }) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const m = useApiMutation<Estimate, string>({
    request: (explanation) => ({ path: `/requests/${ctx.requestId}/estimates`, body: bodyFrom(valuesFrom(latest), explanation) }),
    idempotent: true,
    invalidate: (o) => [qk.requests.detail(o, ctx.requestId), qk.requests.estimates(o, ctx.requestId), qk.estimates.all(o)],
    successMessage: "New draft revision created.",
    onSuccess: () => {
      setOpen(false);
      setText("");
    },
  });
  const withdraw = useApiMutation<Estimate, { reason: string }>({
    request: ({ reason }) => ({ path: `/estimates/${latest.id}/withdraw`, body: { reason } }),
    idempotent: true,
    invalidate: (o) => [qk.requests.detail(o, ctx.requestId), qk.requests.estimates(o, ctx.requestId), qk.estimates.all(o)],
    successMessage: "Estimate withdrawn.",
  });
  const [wd, setWd] = useState(false);
  const canWithdraw = latest.status === "AWAITING_APPROVAL" || latest.status === "REJECTED";
  return (
    <div className="flex flex-wrap gap-2">
      <Button variant="secondary" onClick={() => setOpen(true)}>
        <FilePlus2 className="size-4" aria-hidden /> Create revision
      </Button>
      {canWithdraw && (
        <Button variant="ghost" onClick={() => setWd(true)}>
          <Undo2 className="size-4" aria-hidden /> Withdraw
        </Button>
      )}
      <Dialog
        open={open}
        onOpenChange={setOpen}
        title={`Create revision of version ${latest.version}`}
        description="A new draft is created with the same amounts. The earlier version stays unchanged."
        footer={
          <>
            <Button variant="secondary" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button
              loading={m.isPending}
              onClick={() => {
                if (text.trim().length < 5) {
                  setErr("Explain what changed (at least 5 characters)");
                  return;
                }
                setErr(null);
                m.mutate(text.trim());
              }}
            >
              Create revision
            </Button>
          </>
        }
      >
        <FormField label="Explanation of the change" required error={err ?? undefined}>
          <Textarea rows={3} value={text} onChange={(e) => setText(e.target.value)} />
        </FormField>
      </Dialog>
      <ConfirmDialog
        open={wd}
        onOpenChange={setWd}
        title={`Withdraw version ${latest.version}?`}
        description="The version is marked superseded. If it was awaiting approval, the SLA clock resumes."
        confirmLabel="Withdraw"
        reason={{ minLength: 5 }}
        onConfirm={(reason) => withdraw.mutateAsync({ reason })}
      />
    </div>
  );
}

/** Main column: estimate versions + editor (staff). */
export function EstimatePanel({ ctx }: RequestActionProps) {
  const q = useApiQuery<Estimate[]>({ queryKey: (o) => qk.requests.estimates(o, ctx.requestId), path: `/requests/${ctx.requestId}/estimates` });
  if (q.isLoading) {
    return (
      <Panel title="Estimate">
        <LoadingState label="Loading estimate" />
      </Panel>
    );
  }
  if (q.error) {
    return (
      <Panel title="Estimate">
        <ErrorState error={q.error} onRetry={() => void q.refetch()} />
      </Panel>
    );
  }
  const versions = [...(q.data ?? [])].sort((a, b) => b.version - a.version);
  const latest = versions[0];
  const draft = latest?.status === "DRAFT" ? latest : undefined;
  const history = versions.filter((v) => v.id !== draft?.id);
  const open = ["TRIAGED", "SCHEDULED", "ACCEPTED", "IN_PROGRESS", "BLOCKED", "REOPENED"].includes(ctx.detail.status);
  return (
    <Panel title="Estimate" bodyClassName="flex flex-col gap-5">
      <InlineNote>Amounts are an estimate, not revenue. While a version awaits approval the request SLA pauses.</InlineNote>
      {draft ? (
        <Editor key={draft.id} ctx={ctx} draft={draft} />
      ) : latest ? (
        <>
          {open ? <NewRevision ctx={ctx} latest={latest} /> : <InlineNote>Estimates cannot be changed while the request is {ctx.detail.status.toLowerCase()}.</InlineNote>}
        </>
      ) : open ? (
        <Editor key="new" ctx={ctx} draft={undefined} />
      ) : (
        <InlineNote>No estimate exists and the request is {ctx.detail.status.toLowerCase()}, so one cannot be created.</InlineNote>
      )}
      {history.length > 0 && (
        <section aria-labelledby="est-versions" className="flex flex-col gap-3">
          <h3 id="est-versions" className="text-sm font-semibold">
            Versions
          </h3>
          <ul className="flex flex-col gap-4">
            {history.map((v) => (
              <li key={v.id} className="rounded-lg border border-border p-4">
                <ReadOnly e={v} />
              </li>
            ))}
          </ul>
        </section>
      )}
    </Panel>
  );
}
