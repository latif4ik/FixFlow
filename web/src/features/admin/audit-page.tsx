"use client";

import { ChevronDown, ChevronRight } from "lucide-react";
import { useState } from "react";
import { Button, DateTime, EmptyState, ErrorState, FilterBar, Input, Label, Pagination, Panel, Select, Skeleton } from "@/components/ui";
import type { Page, Schemas } from "@/lib/api";
import { useOrgTimezone } from "@/lib/auth";
import { addDaysYmd, zonedInstant } from "@/features/dashboard/tz";
import { qk, useApiQuery } from "@/lib/query";
import { AdminPage } from "./shared";

type AuditEvent = Schemas["AuditEventOut"];
const PAGE_SIZE = 20;

interface Draft {
  action: string;
  target_type: string;
  actor: string;
  from: string;
  to: string;
}
const EMPTY: Draft = { action: "", target_type: "", actor: "", from: "", to: "" };

const show = (v: unknown): string => (v === null || v === undefined ? "-" : typeof v === "object" ? JSON.stringify(v) : String(v));

/** Readable before -> after table: one row per changed key. */
export function DiffTable({ before, after }: { before: Record<string, unknown> | null; after: Record<string, unknown> | null }) {
  const keys = [...new Set([...Object.keys(before ?? {}), ...Object.keys(after ?? {})])].sort();
  if (keys.length === 0) return <p className="text-[13px] text-muted">No details were recorded for this event.</p>;
  return (
    <table className="w-full text-left text-[13px]">
      <caption className="sr-only">Changed fields, before and after</caption>
      <thead>
        <tr className="text-muted">
          <th scope="col" className="py-1 pr-4 font-semibold">
            Field
          </th>
          <th scope="col" className="py-1 pr-4 font-semibold">
            Before
          </th>
          <th scope="col" className="py-1 font-semibold">
            After
          </th>
        </tr>
      </thead>
      <tbody>
        {keys.map((k) => {
          const changed = show(before?.[k]) !== show(after?.[k]);
          return (
            <tr key={k} className="border-t border-border align-top">
              <th scope="row" className="py-1.5 pr-4 font-mono font-semibold text-ink">
                {k}
              </th>
              <td className="break-all py-1.5 pr-4 text-text">{show(before?.[k])}</td>
              <td className={`break-all py-1.5 ${changed ? "font-semibold text-ink" : "text-text"}`}>{show(after?.[k])}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function EventRow({ e }: { e: AuditEvent }) {
  const [open, setOpen] = useState(false);
  return (
    <li className="border-t border-border first:border-t-0">
      <button type="button" aria-expanded={open} onClick={() => setOpen((o) => !o)} className="flex w-full flex-wrap items-center gap-x-4 gap-y-1 px-5 py-3 text-left text-sm hover:bg-canvas/60">
        {open ? <ChevronDown className="size-4 shrink-0" aria-hidden /> : <ChevronRight className="size-4 shrink-0" aria-hidden />}
        <DateTime value={e.created_at} className="w-40 text-muted" />
        <span className="w-48 font-semibold text-ink">{e.actor_name ?? "System"}</span>
        <span className="font-mono text-[13px] text-primary-dark">{e.action}</span>
        <span className="text-muted">
          {e.target_type}
          {e.target_id ? ` ${e.target_id.slice(0, 8)}` : ""}
        </span>
        <span className="sr-only">{open ? "Hide changes" : "Show changes"}</span>
      </button>
      {open && (
        <div className="bg-canvas/50 px-5 pb-4 pl-12">
          <DiffTable before={e.before} after={e.after} />
        </div>
      )}
    </li>
  );
}

export function AuditPage() {
  const tz = useOrgTimezone();
  const [draft, setDraft] = useState<Draft>(EMPTY);
  const [applied, setApplied] = useState<Draft>(EMPTY);
  const [page, setPage] = useState(1);
  const members = useApiQuery<Page<Schemas["MemberOut"]>>({ queryKey: (o) => qk.members.list(o, { all: true }), path: "/org/members", query: { page_size: 100 } });

  const params = {
    action: applied.action || undefined,
    target_type: applied.target_type || undefined,
    actor: applied.actor || undefined,
    date_from: applied.from ? new Date(zonedInstant(applied.from, 0, 0, tz)).toISOString() : undefined,
    date_to: applied.to ? new Date(zonedInstant(addDaysYmd(applied.to, 1), 0, 0, tz)).toISOString() : undefined,
    page,
    page_size: PAGE_SIZE,
  };
  const q = useApiQuery<Page<AuditEvent>>({ queryKey: (o) => qk.audit.list(o, params), path: "/audit", query: params });
  const set = (k: keyof Draft) => (e: { target: { value: string } }) => setDraft((d) => ({ ...d, [k]: e.target.value }));

  return (
    <AdminPage title="Audit log" description="Every important change: who did it, when, and what changed. Times are in the organization time zone.">
      <FilterBar label="Audit filters">
        <form
          className="flex flex-wrap items-end gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            setApplied(draft);
            setPage(1);
          }}
        >
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="au-action">Action</Label>
            <Input id="au-action" value={draft.action} onChange={set("action")} placeholder="e.g. request.status_change" className="w-60" />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="au-type">Target type</Label>
            <Input id="au-type" value={draft.target_type} onChange={set("target_type")} placeholder="e.g. service_request" className="w-48" />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="au-actor">Actor</Label>
            <Select id="au-actor" value={draft.actor} onChange={set("actor")} className="w-56">
              <option value="">Anyone</option>
              {members.data?.items.map((m) => (
                <option key={m.membership_id} value={m.membership_id}>
                  {m.full_name}
                </option>
              ))}
            </Select>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="au-from">From</Label>
            <Input id="au-from" type="date" value={draft.from} onChange={set("from")} className="w-40" />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="au-to">To</Label>
            <Input id="au-to" type="date" value={draft.to} onChange={set("to")} className="w-40" />
          </div>
          <Button type="submit">Apply filters</Button>
          <Button
            variant="ghost"
            onClick={() => {
              setDraft(EMPTY);
              setApplied(EMPTY);
              setPage(1);
            }}
          >
            Reset
          </Button>
        </form>
      </FilterBar>
      <Panel bodyClassName="p-0">
        {q.error ? (
          <div className="p-5">
            <ErrorState error={q.error} onRetry={() => q.refetch()} />
          </div>
        ) : !q.data ? (
          <div className="p-5">
            <Skeleton className="h-40 w-full" />
          </div>
        ) : q.data.items.length === 0 ? (
          <EmptyState title="No audit events match" description="Try widening the filters." />
        ) : (
          <>
            <ul aria-label="Audit events">
              {q.data.items.map((e) => (
                <EventRow key={e.id} e={e} />
              ))}
            </ul>
            <Pagination page={page} pageSize={PAGE_SIZE} total={q.data.total} onPageChange={setPage} className="border-t border-border" />
          </>
        )}
      </Panel>
    </AdminPage>
  );
}
