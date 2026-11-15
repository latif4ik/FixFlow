"use client";

import { estimateStatusLabel } from "@/lib/labels";
import { zodResolver } from "@hookform/resolvers/zod";
import { EyeOff, Globe, Star } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { z } from "zod";
import { AuthImage, Avatar, Badge, Button, DateTime, Dialog, EmptyState, FormField, FormServerError, Money, Panel, RadioGroup, RadioItem, Textarea } from "@/components/ui";
import type { NoteOut, RequestDetail, Role, TimelineItem } from "@/lib/api/types";
import { newIdempotencyKey } from "@/lib/api/client";
import { cn } from "@/lib/cn";
import { formatDuration } from "@/lib/format";
import { useApiMutation } from "@/lib/query/hooks";
import { qk } from "@/lib/query/keys";
import { STATUS_META } from "@/components/ui";

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs font-semibold uppercase tracking-wide text-subtle">{label}</dt>
      <dd className="mt-0.5 text-sm text-ink">{children}</dd>
    </div>
  );
}

export function FactsPanel({ detail: d, role }: { detail: RequestDetail; role: Role }) {
  return (
    <Panel title="Details">
      <dl className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        <Fact label="Property">
          {role === "REQUESTER" ? (
            d.property.name
          ) : (
            <Link href={`/properties/${d.property.id}`} className="hover:underline">
              {d.property.name}
            </Link>
          )}
          <span className="block text-[13px] text-muted">{d.property.address}</span>
        </Fact>
        <Fact label="Asset">{d.asset ? `${d.asset.code} · ${d.asset.name}` : <span className="text-muted">No asset</span>}</Fact>
        <Fact label="Category">{d.category.name}</Fact>
        <Fact label="Requester">{d.requester?.name ?? <span className="text-muted">Unknown</span>}</Fact>
        <Fact label="Technician and window">
          {d.assignment ? (
            <>
              {d.assignment.technician.name}
              <span className="block text-[13px] text-muted">
                <DateTime value={d.assignment.start_at} style="short" /> to <DateTime value={d.assignment.end_at} style="time" />
              </span>
            </>
          ) : (
            <span className="text-muted">Not assigned yet</span>
          )}
        </Fact>
        <Fact label="Created">
          <DateTime value={d.created_at} />
        </Fact>
        {d.preferred_window_start && (
          <Fact label="Preferred window">
            <DateTime value={d.preferred_window_start} style="short" />
            {d.preferred_window_end && (
              <>
                {" "}
                to <DateTime value={d.preferred_window_end} style="short" />
              </>
            )}
          </Fact>
        )}
        {d.duplicate_of && (
          <Fact label="Duplicate of">
            <Link href={`/requests/${d.duplicate_of.id}`} className="font-semibold text-primary hover:underline">
              {d.duplicate_of.display_id}
            </Link>
          </Fact>
        )}
      </dl>
      <h3 className="mt-5 text-sm font-bold">Description</h3>
      <p className="mt-1 whitespace-pre-wrap text-sm text-text">{d.description}</p>
    </Panel>
  );
}

/* ---------- Messages / notes ---------- */
function NoteItem({ note }: { note: NoteOut }) {
  const internal = note.visibility === "INTERNAL";
  const name = note.author?.name ?? "System";
  return (
    <li className={cn("rounded-lg border p-3.5", internal ? "border-warning/60 bg-warning-tint" : "border-border bg-surface")}>
      <div className="flex flex-wrap items-center gap-2 text-[13px]">
        <Avatar name={name} className="size-6 text-[10px]" />
        <span className="font-semibold text-ink">{name}</span>
        <DateTime value={note.created_at} style="short" className="text-muted" />
        {internal ? (
          <Badge tone="warning" icon={EyeOff}>
            Internal note · hidden from requester
          </Badge>
        ) : (
          <Badge tone="neutral" icon={Globe}>
            Public
          </Badge>
        )}
      </div>
      <p className="mt-2 whitespace-pre-wrap text-sm text-ink">{note.body}</p>
    </li>
  );
}

const noteSchema = z.object({
  body: z.string().trim().min(1, "Write a note first").max(2000, "Notes are limited to 2000 characters"),
  visibility: z.enum(["PUBLIC", "INTERNAL"]),
});
type NoteValues = z.infer<typeof noteSchema>;

function AddNoteForm({ requestId, role }: { requestId: string; role: Role }) {
  const staff = role !== "REQUESTER";
  const form = useForm<NoteValues>({ resolver: zodResolver(noteSchema), defaultValues: { body: "", visibility: "PUBLIC" } });
  const add = useApiMutation<unknown, NoteValues>({
    request: (v) => ({
      path: `/requests/${requestId}/notes`,
      body: { body: v.body, visibility: staff ? v.visibility : "PUBLIC", kind: "GENERAL", client_command_id: newIdempotencyKey() },
    }),
    idempotent: true,
    form,
    successMessage: "Note added.",
    invalidate: (orgId) => [qk.requests.detail(orgId, requestId)],
    onSuccess: () => form.reset({ body: "", visibility: form.getValues("visibility") }),
  });
  const visibility = useWatch({ control: form.control, name: "visibility" });
  return (
    <form noValidate onSubmit={form.handleSubmit((v) => add.mutate(v))} className="mt-4 flex flex-col gap-3 border-t border-border pt-4" aria-label="Add a note">
      <h3 className="text-sm font-bold">Add a note</h3>
      {staff && (
        <RadioGroup aria-label="Visibility" value={visibility} onValueChange={(v) => form.setValue("visibility", v as NoteValues["visibility"])}>
          <RadioItem value="PUBLIC" label="Public, visible to requester" />
          <RadioItem value="INTERNAL" label="Internal, dispatchers only" />
        </RadioGroup>
      )}
      <FormField label="Note text" required error={form.formState.errors.body?.message} hint={staff ? undefined : "Your note is visible to the dispatchers handling this request."}>
        <Textarea rows={3} {...form.register("body")} />
      </FormField>
      <FormServerError form={form} />
      <div>
        <Button type="submit" loading={add.isPending}>
          Add note
        </Button>
      </div>
    </form>
  );
}

export function MessagesPanel({ detail, requestId, role }: { detail: RequestDetail; requestId: string; role: Role }) {
  return (
    <Panel title="Messages">
      {detail.notes.length === 0 ? (
        <EmptyState title="No messages yet" description="Notes added to this request appear here." />
      ) : (
        <ul className="flex flex-col gap-3">
          {detail.notes.map((n) => (
            <NoteItem key={n.id} note={n} />
          ))}
        </ul>
      )}
      {detail.status !== "CLOSED" && detail.status !== "CANCELED" && <AddNoteForm requestId={requestId} role={role} />}
    </Panel>
  );
}

/* ---------- Attachments ---------- */
export function Attachments({ detail }: { detail: RequestDetail }) {
  const [open, setOpen] = useState<{ id: string; name: string } | null>(null);
  const images = detail.files.filter((f) => f.mime_type.startsWith("image/"));
  const others = detail.files.filter((f) => !f.mime_type.startsWith("image/"));
  return (
    <Panel title="Attachments">
      {detail.files.length === 0 ? (
        <p className="text-sm text-muted">No attachments.</p>
      ) : (
        <>
          <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4">
            {images.map((f) => (
              <li key={f.id}>
                <button type="button" onClick={() => setOpen({ id: f.id, name: f.original_filename })} className="block w-full overflow-hidden rounded-lg border border-border" aria-label={`Open ${f.original_filename}`}>
                  <AuthImage fileId={f.id} alt={`Attachment: ${f.original_filename}`} className="h-28 w-full object-cover" />
                </button>
              </li>
            ))}
          </ul>
          {others.length > 0 && (
            <ul className="mt-3 text-sm">
              {others.map((f) => (
                <li key={f.id}>{f.original_filename}</li>
              ))}
            </ul>
          )}
        </>
      )}
      <Dialog open={open !== null} onOpenChange={(o) => !o && setOpen(null)} title={open?.name ?? "Attachment"} className="max-w-3xl">
        {open && <AuthImage fileId={open.id} alt={`Attachment: ${open.name}`} className="max-h-[70vh] w-full object-contain" />}
      </Dialog>
    </Panel>
  );
}

/* ---------- Estimate (read-only), materials, feedback ---------- */
export function EstimateSummaryPanel({ detail }: { detail: RequestDetail }) {
  const e = detail.estimate;
  if (!e) return null;
  return (
    <Panel title="Estimate" actions={<Badge tone="neutral">{`Version ${e.version} · ${estimateStatusLabel(e.status)}`}</Badge>}>
      <ul className="divide-y divide-border text-sm">
        {e.lines.map((l) => (
          <li key={l.id} className="flex items-start justify-between gap-3 py-2">
            <span>
              {l.description}
              <span className="block text-[13px] text-muted">
                {l.quantity} × <Money minor={l.unit_price_minor} currency={e.currency} />
              </span>
            </span>
            <Money minor={l.line_total_minor} currency={e.currency} />
          </li>
        ))}
      </ul>
      <dl className="mt-3 space-y-1 border-t border-border pt-3 text-sm">
        <div className="flex justify-between">
          <dt>Labor ({formatDuration(e.labor_minutes)})</dt>
          <dd>
            <Money minor={e.labor_cost_minor} currency={e.currency} />
          </dd>
        </div>
        <div className="flex justify-between">
          <dt>Materials</dt>
          <dd>
            <Money minor={e.materials_total_minor} currency={e.currency} />
          </dd>
        </div>
        <div className="flex justify-between font-bold text-ink">
          <dt>Estimate total</dt>
          <dd>
            <Money minor={e.total_minor} currency={e.currency} />
          </dd>
        </div>
      </dl>
      <p className="mt-3 text-xs text-muted">Amounts are an estimate, not revenue.</p>
    </Panel>
  );
}

export function MaterialsPanel({ detail }: { detail: RequestDetail }) {
  const items = detail.materials;
  if (!items || items.length === 0) return null;
  const total = items.reduce((sum, i) => sum + i.total_cost_minor, 0);
  return (
    <Panel title="Materials used">
      <ul className="divide-y divide-border text-sm">
        {items.map((i) => (
          <li key={i.id} className="flex justify-between gap-3 py-2">
            <span>
              {i.item.name}{" "}
              <span className="text-muted">
                × {i.quantity} {i.item.unit}
              </span>
            </span>
            <Money minor={i.total_cost_minor} currency={i.currency} />
          </li>
        ))}
      </ul>
      <p className="mt-3 flex justify-between border-t border-border pt-3 text-sm font-bold text-ink">
        <span>Total cost</span>
        <Money minor={total} currency={items[0]?.currency} />
      </p>
    </Panel>
  );
}

export function FeedbackPanel({ detail }: { detail: RequestDetail }) {
  const f = detail.feedback;
  if (!f) return null;
  return (
    <Panel title="Feedback">
      <p className="flex items-center gap-1 text-sm font-semibold text-ink" aria-label={`Rating ${f.rating} out of 5`}>
        {Array.from({ length: 5 }).map((_, i) => (
          <Star key={i} aria-hidden className={cn("size-4", i < f.rating ? "fill-warning text-warning" : "text-border-strong")} />
        ))}
        <span className="ml-1">{f.rating} / 5</span>
      </p>
      {f.comment && <p className="mt-2 whitespace-pre-wrap text-sm text-text">{f.comment}</p>}
    </Panel>
  );
}

/* ---------- Activity timeline ---------- */
function describe(t: TimelineItem): string {
  const to = t.to_status ? STATUS_META[t.to_status as keyof typeof STATUS_META]?.label : undefined;
  const from = t.from_status ? STATUS_META[t.from_status as keyof typeof STATUS_META]?.label : undefined;
  const data = (t.data ?? {}) as Record<string, unknown>;
  switch (t.type) {
    case "STATUS_CHANGED":
      return from && to ? `Status changed from ${from} to ${to}` : to ? `Status changed to ${to}` : t.label;
    case "REQUEST_CREATED":
      return "Request submitted";
    case "ASSIGNED": {
      const tech = (data.technician as { name?: string } | undefined)?.name;
      return tech ? `Assigned to ${tech}` : t.label;
    }
    case "PRIORITY_CHANGED":
      return `Priority changed${data.from ? ` from ${String(data.from)}` : ""}${data.to ? ` to ${String(data.to)}` : ""}`;
    default: {
      if (typeof data.reason === "string" && data.reason) return `${t.label}. Reason: ${data.reason}`;
      return t.label;
    }
  }
}

export function Activity({ detail }: { detail: RequestDetail }) {
  const items = [...detail.timeline].sort((a, b) => b.created_at.localeCompare(a.created_at));
  return (
    <Panel title="Activity">
      <ol className="relative flex flex-col gap-4 border-l border-border pl-4">
        {items.map((t) => (
          <li key={t.id} className="relative text-sm">
            <span aria-hidden className="absolute -left-[21px] top-1.5 size-2.5 rounded-pill border-2 border-surface bg-primary" />
            <p className="font-semibold text-ink">{describe(t)}</p>
            <p className="text-[13px] text-muted">
              {t.actor?.name ?? "System"} · <DateTime value={t.created_at} style="short" />
            </p>
          </li>
        ))}
      </ol>
    </Panel>
  );
}
