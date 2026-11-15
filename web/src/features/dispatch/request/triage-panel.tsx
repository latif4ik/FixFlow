"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { ClipboardCheck, Copy, Search } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { Badge, Button, FormField, FormServerError, InlineNote, Input, Panel, Select, Textarea } from "@/components/ui";
import type { Page, Priority, RequestListItem, Schemas } from "@/lib/api/types";
import { useApiMutation, useApiQuery } from "@/lib/query/hooks";
import { qk } from "@/lib/query/keys";
import type { RequestActionProps } from "@/features/request-actions/types";

const reasonSchema = z.string().trim().min(5, "Enter a reason of at least 5 characters").max(500, "At most 500 characters");

const editSchema = z
  .object({ priority: z.enum(["LOW", "NORMAL", "HIGH"]), category_id: z.string().min(1), reason: reasonSchema })
  .strict();
type EditValues = z.infer<typeof editSchema>;

const PRIORITIES: { value: Priority; label: string }[] = [
  { value: "HIGH", label: "High" },
  { value: "NORMAL", label: "Normal" },
  { value: "LOW", label: "Low" },
];

function MarkTriaged({ ctx }: RequestActionProps) {
  const [note, setNote] = useState("");
  const m = useApiMutation<unknown, { note?: string }>({
    request: (v) => ({ path: `/requests/${ctx.requestId}/triage`, body: v }),
    idempotent: true,
    invalidate: (o) => [qk.requests.detail(o, ctx.requestId), qk.requests.all(o)],
    successMessage: "Request marked as triaged.",
    onSuccess: () => setNote(""),
  });
  return (
    <form
      aria-label="Mark triaged"
      className="flex flex-col gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        m.mutate(note.trim() ? { note: note.trim() } : {});
      }}
    >
      <FormField label="Triage note (optional)" hint="Saved as an internal note. The requester does not see it.">
        <Textarea rows={3} maxLength={2000} value={note} onChange={(e) => setNote(e.target.value)} />
      </FormField>
      <Button type="submit" loading={m.isPending}>
        <ClipboardCheck className="size-4" aria-hidden /> Mark triaged
      </Button>
    </form>
  );
}

function EditCategoryPriority({ ctx }: RequestActionProps) {
  const { detail } = ctx;
  const cats = useApiQuery<Page<Schemas["CategoryOut"]>>({ queryKey: (o) => qk.categories.list(o, { page_size: 100 }), path: "/categories", query: { page_size: 100 }, staleTime: 60_000 });
  const form = useForm<EditValues>({
    resolver: zodResolver(editSchema),
    defaultValues: { priority: detail.priority, category_id: detail.category.id, reason: "" },
  });
  const m = useApiMutation<unknown, EditValues>({
    request: (v) => ({
      method: "PATCH",
      path: `/requests/${ctx.requestId}`,
      body: {
        ...(v.priority !== detail.priority ? { priority: v.priority } : {}),
        ...(v.category_id !== detail.category.id ? { category_id: v.category_id } : {}),
        reason: v.reason,
      },
    }),
    invalidate: (o) => [qk.requests.detail(o, ctx.requestId), qk.requests.all(o)],
    successMessage: "Request updated.",
    form,
    onSuccess: () => form.resetField("reason", { defaultValue: "" }),
  });
  const errs = form.formState.errors;
  return (
    <form
      aria-label="Change category or priority"
      className="flex flex-col gap-3"
      noValidate
      onSubmit={form.handleSubmit((v) => {
        if (v.priority === detail.priority && v.category_id === detail.category.id) {
          form.setError("root.server", { message: "Change the category or the priority first." });
          return;
        }
        m.mutate(v);
      })}
    >
      <FormServerError form={form} />
      <FormField label="Category" error={errs.category_id?.message}>
        <Select {...form.register("category_id")}>
          {!cats.data && <option value={detail.category.id}>{detail.category.name}</option>}
          {cats.data?.items.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </Select>
      </FormField>
      <FormField label="Priority" error={errs.priority?.message}>
        <Select {...form.register("priority")}>
          {PRIORITIES.map((p) => (
            <option key={p.value} value={p.value}>
              {p.label}
            </option>
          ))}
        </Select>
      </FormField>
      <FormField label="Reason for the change" required error={errs.reason?.message} hint="Recorded in the activity log. Changing the category may change the SLA.">
        <Textarea rows={2} {...form.register("reason")} />
      </FormField>
      <Button type="submit" variant="secondary" loading={m.isPending}>
        Save change
      </Button>
    </form>
  );
}

function LinkDuplicate({ ctx }: RequestActionProps) {
  const [term, setTerm] = useState("");
  const [query, setQuery] = useState("");
  const [picked, setPicked] = useState<RequestListItem | null>(null);
  const [reason, setReason] = useState("");
  const [reasonError, setReasonError] = useState<string | null>(null);
  const search = useApiQuery<Page<RequestListItem>>({
    queryKey: (o) => qk.requests.list(o, { q: query, page_size: 5, purpose: "duplicate-search" }),
    path: "/requests",
    query: { q: query, page_size: 5 },
    enabled: query.length >= 1,
  });
  const m = useApiMutation<unknown, { duplicate_of_id: string; reason: string }>({
    request: (v) => ({ path: `/requests/${ctx.requestId}/duplicate`, body: v }),
    idempotent: true,
    invalidate: (o) => [qk.requests.detail(o, ctx.requestId), qk.requests.all(o)],
    successMessage: "Linked as a duplicate.",
    onSuccess: () => {
      setPicked(null);
      setReason("");
    },
  });
  const results = (search.data?.items ?? []).filter((r) => r.id !== ctx.requestId);
  return (
    <div className="flex flex-col gap-3">
      <form
        role="search"
        aria-label="Find the original request"
        className="flex items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          setQuery(term.trim());
          setPicked(null);
        }}
      >
        <FormField label="Original request" hint="Search by REQ id or title, e.g. REQ-12" className="flex-1">
          <Input value={term} onChange={(e) => setTerm(e.target.value)} />
        </FormField>
        <Button type="submit" variant="secondary" aria-label="Search requests">
          <Search className="size-4" aria-hidden />
        </Button>
      </form>
      {query && !search.isLoading && results.length === 0 && <InlineNote>No other request matches &ldquo;{query}&rdquo;.</InlineNote>}
      {results.length > 0 && (
        <ul aria-label="Matching requests" className="flex flex-col gap-1">
          {results.map((r) => (
            <li key={r.id}>
              <button
                type="button"
                aria-pressed={picked?.id === r.id}
                onClick={() => setPicked(r)}
                className={`w-full rounded-md border px-3 py-2 text-left text-sm ${picked?.id === r.id ? "border-primary bg-primary-tint" : "border-border hover:bg-canvas"}`}
              >
                <span className="font-semibold">{r.display_id}</span> · {r.title}
              </button>
            </li>
          ))}
        </ul>
      )}
      {picked && (
        <form
          aria-label="Link duplicate"
          className="flex flex-col gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            const r = reason.trim();
            if (r.length < 5) {
              setReasonError("Enter a reason of at least 5 characters");
              return;
            }
            setReasonError(null);
            m.mutate({ duplicate_of_id: picked.id, reason: r });
          }}
        >
          <FormField label={`Why is this a duplicate of ${picked.display_id}?`} required error={reasonError ?? undefined}>
            <Textarea rows={2} value={reason} onChange={(e) => setReason(e.target.value)} />
          </FormField>
          <Button type="submit" variant="secondary" loading={m.isPending}>
            <Copy className="size-4" aria-hidden /> Link as duplicate of {picked.display_id}
          </Button>
        </form>
      )}
    </div>
  );
}

function TriageNote({ ctx }: RequestActionProps) {
  const [body, setBody] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const m = useApiMutation<unknown, { body: string }>({
    request: (v) => ({ path: `/requests/${ctx.requestId}/notes`, body: { body: v.body, visibility: "INTERNAL", kind: "TRIAGE" } }),
    idempotent: true,
    invalidate: (o) => [qk.requests.detail(o, ctx.requestId)],
    successMessage: "Triage note added.",
    onSuccess: () => setBody(""),
  });
  return (
    <form
      aria-label="Add triage note"
      className="flex flex-col gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        if (!body.trim()) {
          setErr("Write a note first");
          return;
        }
        setErr(null);
        m.mutate({ body: body.trim() });
      }}
    >
      <FormField label="Triage note" error={err ?? undefined} hint="Internal: hidden from the requester.">
        <Textarea rows={2} maxLength={2000} value={body} onChange={(e) => setBody(e.target.value)} />
      </FormField>
      <Button type="submit" variant="secondary" loading={m.isPending}>
        Add note
      </Button>
    </form>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="flex flex-col gap-3 border-t border-border pt-4 first:border-t-0 first:pt-0">
      <h3 className="text-sm font-semibold">{title}</h3>
      {children}
    </section>
  );
}

/** Sidebar: triage (mark triaged, category/priority with reason, duplicates, triage note). */
export function TriagePanel({ ctx }: RequestActionProps) {
  const { detail, allowed } = ctx;
  const canTriage = allowed.has("triage");
  const canEdit = allowed.has("edit_priority_category");
  const canDup = allowed.has("link_duplicate");
  const canNote = allowed.has("add_note");
  return (
    <Panel title="Triage" bodyClassName="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        {detail.status === "SUBMITTED" ? (
          <Badge tone="warning">Waiting for triage</Badge>
        ) : (
          <Badge tone="success" icon={ClipboardCheck}>
            Triaged
          </Badge>
        )}
        {detail.duplicate_of && (
          <Badge tone="neutral" icon={Copy}>
            Duplicate of {detail.duplicate_of.display_id}
          </Badge>
        )}
      </div>
      {canTriage ? (
        <Section title="Mark as triaged">
          <MarkTriaged ctx={ctx} />
        </Section>
      ) : (
        detail.status !== "SUBMITTED" && <p className="text-[13px] text-muted">Triage is only available while a request is Submitted. It is now {detail.status.toLowerCase().replaceAll("_", " ")}.</p>
      )}
      {canEdit && (
        <Section title="Category and priority">
          <EditCategoryPriority ctx={ctx} />
        </Section>
      )}
      {canDup && !detail.duplicate_of && (
        <Section title="Link duplicate">
          <LinkDuplicate ctx={ctx} />
        </Section>
      )}
      {canNote && (
        <Section title="Triage note">
          <TriageNote ctx={ctx} />
        </Section>
      )}
    </Panel>
  );
}
