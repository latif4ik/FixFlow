"use client";

import { Plus, Search } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { Button, DataTable, DateTime, EmptyState, FilterBar, Input, Label, PageHeader, PriorityBadge, Select, StatusBadge, buttonStyles } from "@/components/ui";
import type { Column } from "@/components/ui";
import { STATUS_META } from "@/components/ui/display";
import { cn } from "@/lib/cn";
import { REQUEST_STATUSES } from "@/lib/api/types";
import type { Page, Priority, RequestListItem, RequestStatus } from "@/lib/api/types";
import { useApiQuery } from "@/lib/query/hooks";
import { qk } from "@/lib/query/keys";

const PAGE_SIZE = 20;
const PRIORITIES: Priority[] = ["HIGH", "NORMAL", "LOW"];
const SORTS = [
  { value: "newest", label: "Newest first" },
  { value: "oldest", label: "Oldest first" },
  { value: "priority", label: "Priority" },
] as const;
type Sort = (typeof SORTS)[number]["value"];

function Chip({ pressed, onClick, children }: { pressed: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      aria-pressed={pressed}
      onClick={onClick}
      className={cn(
        "rounded-pill border px-3 py-1 text-[13px] font-semibold transition-colors",
        pressed ? "border-primary bg-primary-tint text-primary-dark" : "border-border-strong bg-surface text-text hover:bg-canvas",
      )}
    >
      {children}
    </button>
  );
}

function NewRequestButton() {
  return (
    <Link href="/requests/new" className={buttonStyles({ variant: "primary", size: "md" })}>
      <Plus className="size-4" aria-hidden /> New request
    </Link>
  );
}

export function MyRequestsPage() {
  const router = useRouter();
  const pathname = usePathname();
  const sp = useSearchParams();

  const q = sp.get("q") ?? "";
  const statuses = sp.getAll("status").filter((s): s is RequestStatus => (REQUEST_STATUSES as string[]).includes(s));
  const priorities = sp.getAll("priority").filter((p): p is Priority => (PRIORITIES as string[]).includes(p));
  const sortParam = sp.get("sort");
  const sort: Sort = SORTS.some((s) => s.value === sortParam) ? (sortParam as Sort) : "newest";
  const page = Math.max(1, Number(sp.get("page")) || 1);

  function update(next: { q?: string; status?: string[]; priority?: string[]; sort?: string; page?: number }) {
    const p = new URLSearchParams();
    const nq = next.q ?? q;
    const ns = next.status ?? statuses;
    const np = next.priority ?? priorities;
    const nsort = next.sort ?? sort;
    const npage = next.page ?? 1;
    if (nq) p.set("q", nq);
    ns.forEach((s) => p.append("status", s));
    np.forEach((s) => p.append("priority", s));
    if (nsort !== "newest") p.set("sort", nsort);
    if (npage > 1) p.set("page", String(npage));
    const qs = p.toString();
    router.replace(qs ? `${pathname}?${qs}` : pathname);
  }

  // Search box: local draft, pushed to the URL after a short pause.
  // `draft === null` means "show the URL value".
  const [draft, setDraft] = useState<string | null>(null);
  useEffect(() => {
    if (draft === null) return;
    const t = setTimeout(() => {
      if (draft.trim() !== q) update({ q: draft.trim() });
      setDraft(null);
    }, 350);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft]);

  const params = { q: q || undefined, status: statuses, priority: priorities, sort, page, page_size: PAGE_SIZE };
  const list = useApiQuery<Page<RequestListItem>>({
    queryKey: (o) => qk.requests.list(o, params),
    path: "/requests",
    query: params,
    placeholderData: (prev) => prev,
  });

  const filtered = Boolean(q) || statuses.length > 0 || priorities.length > 0;
  const toggle = <T extends string>(arr: T[], v: T) => (arr.includes(v) ? arr.filter((x) => x !== v) : [...arr, v]);

  const columns: Column<RequestListItem>[] = [
    { key: "id", header: "Request", cell: (r) => <span className="font-semibold text-muted">{r.display_id}</span> },
    {
      key: "title",
      header: "Title",
      cell: (r) => (
        <Link href={`/requests/${r.id}`} className="font-semibold text-ink hover:text-primary-dark hover:underline">
          {r.title}
        </Link>
      ),
      className: "min-w-56",
    },
    { key: "status", header: "Status", cell: (r) => <StatusBadge status={r.status} /> },
    { key: "priority", header: "Priority", cell: (r) => <PriorityBadge priority={r.priority} /> },
    { key: "property", header: "Property", cell: (r) => r.property.name },
    { key: "updated", header: "Updated", cell: (r) => <DateTime value={r.updated_at} style="short" /> },
  ];

  return (
    <>
      <PageHeader title="My requests" description="Track the maintenance requests you have submitted." actions={<NewRequestButton />} />
      <FilterBar label="Filter requests">
        <div className="flex min-w-56 flex-1 flex-col gap-1.5">
          <Label htmlFor="req-search">Search</Label>
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-3 size-4 text-subtle" aria-hidden />
            <Input id="req-search" type="search" className="pl-9" placeholder="Search by title or REQ number" value={draft ?? q} onChange={(e) => setDraft(e.target.value)} />
          </div>
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="req-sort">Sort by</Label>
          <Select id="req-sort" value={sort} onChange={(e) => update({ sort: e.target.value })}>
            {SORTS.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </Select>
        </div>
        <fieldset className="flex w-full flex-col gap-1.5">
          <legend className="mb-1.5 text-[13px] font-semibold text-ink">Status</legend>
          <div className="flex flex-wrap gap-2">
            {REQUEST_STATUSES.map((s) => (
              <Chip key={s} pressed={statuses.includes(s)} onClick={() => update({ status: toggle(statuses, s) })}>
                {STATUS_META[s].label}
              </Chip>
            ))}
          </div>
        </fieldset>
        <fieldset className="flex w-full flex-col gap-1.5">
          <legend className="mb-1.5 text-[13px] font-semibold text-ink">Priority</legend>
          <div className="flex flex-wrap items-center gap-2">
            {PRIORITIES.map((p) => (
              <Chip key={p} pressed={priorities.includes(p)} onClick={() => update({ priority: toggle(priorities, p) })}>
                {p.charAt(0) + p.slice(1).toLowerCase()}
              </Chip>
            ))}
            {filtered && (
              <Button variant="ghost" size="sm" onClick={() => { setDraft(null); update({ q: "", status: [], priority: [] }); }}>
                Clear filters
              </Button>
            )}
          </div>
        </fieldset>
      </FilterBar>

      <DataTable
        caption="My requests"
        columns={columns}
        rows={list.data?.items}
        rowKey={(r) => r.id}
        loading={list.isLoading}
        error={list.error}
        onRetry={() => void list.refetch()}
        page={page}
        pageSize={PAGE_SIZE}
        total={list.data?.total ?? 0}
        onPageChange={(p) => update({ page: p })}
        empty={
          filtered ? (
            <EmptyState
              title="No requests match these filters"
              description="Try a different search or clear the filters."
              action={
                <Button variant="secondary" onClick={() => { setDraft(null); update({ q: "", status: [], priority: [] }); }}>
                  Clear filters
                </Button>
              }
            />
          ) : (
            <EmptyState title="You have no requests yet" description="When something needs fixing, submit a request and follow its progress here." action={<NewRequestButton />} />
          )
        }
      />
    </>
  );
}
