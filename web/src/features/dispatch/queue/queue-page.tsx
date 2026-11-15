"use client";

import { ChevronDown, Search } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import {
  Button,
  Checkbox,
  DataTable,
  DateTime,
  EmptyState,
  FilterBar,
  FormField,
  Input,
  PageHeader,
  Popover,
  PopoverContent,
  PopoverTrigger,
  PriorityBadge,
  Select,
  SlaBadge,
  StatusBadge,
} from "@/components/ui";
import type { Column } from "@/components/ui";
import type { Page, RequestListItem, RequestStatus, Schemas } from "@/lib/api/types";
import { REQUEST_STATUSES } from "@/lib/api/types";
import { useApiQuery } from "@/lib/query/hooks";
import { qk } from "@/lib/query/keys";
import { STATUS_META } from "@/components/ui";

export const PAGE_SIZE = 20;
const SLA_STATES = [
  { value: "ON_TRACK", label: "On track" },
  { value: "AT_RISK", label: "At risk" },
  { value: "OVERDUE", label: "Overdue" },
  { value: "PAUSED", label: "Paused" },
];
const SORTS = [
  { value: "newest", label: "Newest first" },
  { value: "oldest", label: "Oldest first" },
  { value: "priority", label: "Highest priority" },
  { value: "due", label: "SLA due soonest" },
];

export interface QueueFilters {
  q: string;
  status: string[];
  priority: string;
  category_id: string;
  property_id: string;
  technician_id: string;
  sla_state: string[];
  sort: string;
  page: number;
}

export function filtersFromSearch(sp: URLSearchParams): QueueFilters {
  const page = Number(sp.get("page") ?? "1");
  return {
    q: sp.get("q") ?? "",
    status: sp.getAll("status"),
    priority: sp.get("priority") ?? "",
    category_id: sp.get("category_id") ?? "",
    property_id: sp.get("property_id") ?? "",
    technician_id: sp.get("technician_id") ?? "",
    sla_state: sp.getAll("sla_state"),
    sort: sp.get("sort") ?? "newest",
    page: Number.isInteger(page) && page > 0 ? page : 1,
  };
}

/** Filters -> API query params (also what is mirrored in the URL). */
export function toApiParams(f: QueueFilters) {
  return {
    q: f.q || undefined,
    status: f.status.length ? f.status : undefined,
    priority: f.priority || undefined,
    category_id: f.category_id || undefined,
    property_id: f.property_id || undefined,
    technician_id: f.technician_id || undefined,
    sla_state: f.sla_state.length ? f.sla_state : undefined,
    sort: f.sort === "newest" ? undefined : f.sort,
    page: f.page > 1 ? f.page : undefined,
  };
}

function toQueryString(params: Record<string, unknown>): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === "") continue;
    if (Array.isArray(v)) v.forEach((x) => sp.append(k, String(x)));
    else sp.set(k, String(v));
  }
  return sp.toString();
}

function MultiSelect({ label, options, value, onChange }: { label: string; options: { value: string; label: string }[]; value: string[]; onChange: (v: string[]) => void }) {
  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-[13px] font-semibold text-ink">{label}</span>
      <Popover>
        <PopoverTrigger asChild>
          <Button variant="secondary" className="min-w-36 justify-between font-normal" aria-label={`${label}: ${value.length ? `${value.length} selected` : "any"}`}>
            {value.length ? `${value.length} selected` : "Any"}
            <ChevronDown className="size-4" aria-hidden />
          </Button>
        </PopoverTrigger>
        <PopoverContent align="start" className="w-60 p-3">
          <fieldset className="flex flex-col gap-2">
            <legend className="sr-only">{label}</legend>
            {options.map((o) => (
              <label key={o.value} className="flex cursor-pointer items-center gap-2.5 text-sm">
                <Checkbox
                  checked={value.includes(o.value)}
                  onCheckedChange={(c) => onChange(c === true ? [...value, o.value] : value.filter((x) => x !== o.value))}
                  aria-label={o.label}
                />
                {o.label}
              </label>
            ))}
          </fieldset>
        </PopoverContent>
      </Popover>
    </div>
  );
}

function sameSet(a: string[], b: string[]) {
  return a.length === b.length && a.every((x) => b.includes(x));
}

export function QueuePage() {
  const router = useRouter();
  const pathname = usePathname();
  const sp = useSearchParams();
  const f = filtersFromSearch(new URLSearchParams(sp.toString()));
  const [draft, setDraft] = useState<string | null>(null);
  const searchText = draft ?? f.q;

  function go(next: Partial<QueueFilters>, resetPage = true) {
    const merged = { ...f, ...next, page: next.page ?? (resetPage ? 1 : f.page) };
    const qs = toQueryString(toApiParams(merged));
    router.replace(qs ? `${pathname}?${qs}` : pathname);
  }

  const params = { ...toApiParams(f), page: f.page, page_size: PAGE_SIZE };
  const list = useApiQuery<Page<RequestListItem>>({ queryKey: (o) => qk.requests.list(o, params), path: "/requests", query: params, placeholderData: (prev) => prev });
  const cats = useApiQuery<Page<Schemas["CategoryOut"]>>({ queryKey: (o) => qk.categories.list(o, { page_size: 100 }), path: "/categories", query: { page_size: 100 }, staleTime: 60_000 });
  const props = useApiQuery<Page<Schemas["PropertyOut"]>>({ queryKey: (o) => qk.properties.list(o, { page_size: 100 }), path: "/properties", query: { page_size: 100 }, staleTime: 60_000 });
  const techs = useApiQuery<Page<Schemas["TechnicianOut"]>>({ queryKey: (o) => qk.technicians.list(o, { page_size: 100 }), path: "/technicians", query: { page_size: 100 }, staleTime: 60_000 });

  const unassigned = sameSet(f.status, ["TRIAGED"]) && f.sla_state.length === 0;
  const overdue = sameSet(f.sla_state, ["OVERDUE"]) && f.status.length === 0;
  const atRisk = sameSet(f.sla_state, ["AT_RISK"]) && f.status.length === 0;

  const columns: Column<RequestListItem>[] = [
    {
      key: "id",
      header: "Request",
      cell: (r) => (
        <Link href={`/requests/${r.id}`} className="font-semibold text-primary-dark hover:underline">
          {r.display_id}
        </Link>
      ),
    },
    {
      key: "title",
      header: "Title",
      className: "min-w-56",
      cell: (r) => (
        <Link href={`/requests/${r.id}`} className="font-medium text-ink hover:underline">
          {r.title}
          <span className="mt-0.5 block text-xs font-normal text-muted">{r.category.name}</span>
        </Link>
      ),
    },
    {
      key: "property",
      header: "Property",
      cell: (r) => (
        <>
          <span className="block">{r.property.name}</span>
          {r.asset && <span className="block text-xs text-muted">{r.asset.code}</span>}
        </>
      ),
    },
    { key: "status", header: "Status", cell: (r) => <StatusBadge status={r.status} /> },
    { key: "priority", header: "Priority", cell: (r) => <PriorityBadge priority={r.priority} /> },
    {
      key: "sla",
      header: "SLA",
      cell: (r) => (r.status === "CLOSED" || r.status === "CANCELED" ? <span className="text-muted">-</span> : <SlaBadge state={r.sla_state} dueAt={r.sla_due_at} />),
    },
    { key: "created", header: "Created", cell: (r) => <DateTime value={r.created_at} style="short" /> },
  ];

  const filtered = Object.values(toApiParams({ ...f, page: 1 })).some((v) => v !== undefined);

  return (
    <>
      <PageHeader title="Request queue" description="Search, filter and triage every request in your organization." />

      <div className="mb-3 flex flex-wrap items-center gap-2" role="group" aria-label="Quick filters">
        <Button size="sm" variant={unassigned ? "primary" : "secondary"} aria-pressed={unassigned} onClick={() => go(unassigned ? { status: [] } : { status: ["TRIAGED"], sla_state: [] })}>
          Unassigned
        </Button>
        <Button size="sm" variant={overdue ? "primary" : "secondary"} aria-pressed={overdue} onClick={() => go(overdue ? { sla_state: [] } : { sla_state: ["OVERDUE"], status: [] })}>
          Overdue
        </Button>
        <Button size="sm" variant={atRisk ? "primary" : "secondary"} aria-pressed={atRisk} onClick={() => go(atRisk ? { sla_state: [] } : { sla_state: ["AT_RISK"], status: [] })}>
          At risk
        </Button>
        {filtered && (
          <Button size="sm" variant="ghost" onClick={() => router.replace(pathname)}>
            Clear filters
          </Button>
        )}
      </div>

      <FilterBar label="Queue filters">
        <form
          role="search"
          aria-label="Search requests"
          className="flex min-w-60 flex-1 items-end gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            go({ q: searchText.trim() });
            setDraft(null);
          }}
        >
          <FormField label="Search" className="flex-1">
            <Input type="search" placeholder="REQ id, title or address" value={searchText} onChange={(e) => setDraft(e.target.value)} />
          </FormField>
          <Button type="submit" variant="secondary" aria-label="Search">
            <Search className="size-4" aria-hidden />
          </Button>
        </form>
        <MultiSelect
          label="Status"
          value={f.status}
          onChange={(v) => go({ status: v })}
          options={REQUEST_STATUSES.map((s: RequestStatus) => ({ value: s, label: STATUS_META[s].label }))}
        />
        <MultiSelect label="SLA state" value={f.sla_state} onChange={(v) => go({ sla_state: v })} options={SLA_STATES} />
        <FormField label="Priority">
          <Select value={f.priority} onChange={(e) => go({ priority: e.target.value })}>
            <option value="">Any</option>
            <option value="HIGH">High</option>
            <option value="NORMAL">Normal</option>
            <option value="LOW">Low</option>
          </Select>
        </FormField>
        <FormField label="Category">
          <Select value={f.category_id} onChange={(e) => go({ category_id: e.target.value })}>
            <option value="">Any</option>
            {cats.data?.items.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField label="Property">
          <Select value={f.property_id} onChange={(e) => go({ property_id: e.target.value })}>
            <option value="">Any</option>
            {props.data?.items.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField label="Technician">
          <Select value={f.technician_id} onChange={(e) => go({ technician_id: e.target.value })}>
            <option value="">Any</option>
            {techs.data?.items.map((t) => (
              <option key={t.membership_id} value={t.membership_id}>
                {t.full_name}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField label="Sort by">
          <Select value={f.sort} onChange={(e) => go({ sort: e.target.value })}>
            {SORTS.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </Select>
        </FormField>
      </FilterBar>

      <DataTable
        caption="Requests"
        columns={columns}
        rows={list.data?.items}
        rowKey={(r) => r.id}
        loading={list.isLoading}
        error={list.error}
        onRetry={() => void list.refetch()}
        page={list.data?.page ?? f.page}
        pageSize={PAGE_SIZE}
        total={list.data?.total}
        onPageChange={(p) => go({ page: p }, false)}
        empty={<EmptyState title={filtered ? "No requests match these filters" : "No requests yet"} description={filtered ? "Try removing a filter or searching for something else." : undefined} />}
      />
    </>
  );
}
