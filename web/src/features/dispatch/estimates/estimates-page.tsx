"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Badge, DataTable, DateTime, EmptyState, FilterBar, FormField, Money, PageHeader, Select } from "@/components/ui";
import type { Column } from "@/components/ui";
import type { Page, RequestListItem, Schemas } from "@/lib/api/types";
import { useApiQuery } from "@/lib/query/hooks";
import { qk } from "@/lib/query/keys";

type Estimate = Schemas["EstimateOut"];
const PAGE_SIZE = 20;
const STATUSES: { value: Estimate["status"]; label: string; tone: "neutral" | "warning" | "success" | "danger" }[] = [
  { value: "DRAFT", label: "Draft", tone: "neutral" },
  { value: "AWAITING_APPROVAL", label: "Awaiting approval", tone: "warning" },
  { value: "APPROVED", label: "Approved", tone: "success" },
  { value: "REJECTED", label: "Rejected", tone: "danger" },
  { value: "SUPERSEDED", label: "Superseded", tone: "neutral" },
];

export function EstimatesPage() {
  const router = useRouter();
  const pathname = usePathname();
  const sp = useSearchParams();
  const status = sp.get("status") ?? "";
  const page = Math.max(1, Number(sp.get("page") ?? "1") || 1);
  const params = { status: status || undefined, page, page_size: PAGE_SIZE };
  const q = useApiQuery<Page<Estimate>>({ queryKey: (o) => qk.estimates.list(o, params), path: "/estimates", query: params, placeholderData: (p) => p });
  // The estimates API only returns the request id; resolve REQ-numbers from the newest requests when possible.
  const reqs = useApiQuery<Page<RequestListItem>>({ queryKey: (o) => qk.requests.list(o, { page_size: 100, purpose: "estimate-labels" }), path: "/requests", query: { page_size: 100 }, staleTime: 60_000 });
  const label = new Map((reqs.data?.items ?? []).map((r) => [r.id, r.display_id]));

  function go(next: { status?: string; page?: number }) {
    const n = new URLSearchParams();
    const s = next.status ?? status;
    const p = next.page ?? 1;
    if (s) n.set("status", s);
    if (p > 1) n.set("page", String(p));
    const qs = n.toString();
    router.replace(qs ? `${pathname}?${qs}` : pathname);
  }

  const columns: Column<Estimate>[] = [
    {
      key: "req",
      header: "Request",
      cell: (e) => (
        <Link href={`/requests/${e.request_id}`} className="font-semibold text-primary-dark hover:underline">
          {label.get(e.request_id) ?? "Open request"}
        </Link>
      ),
    },
    { key: "version", header: "Version", cell: (e) => `v${e.version}` },
    {
      key: "status",
      header: "Status",
      cell: (e) => {
        const m = STATUSES.find((s) => s.value === e.status)!;
        return <Badge tone={m.tone}>{m.label}</Badge>;
      },
    },
    { key: "total", header: "Total", className: "text-right", cell: (e) => <Money minor={e.total_minor} currency={e.currency} /> },
    { key: "updated", header: "Last activity", cell: (e) => <DateTime value={e.decided_at ?? e.submitted_at ?? e.created_at} style="short" /> },
  ];

  return (
    <>
      <PageHeader title="Estimates" description="Every estimate version across requests. Amounts are estimates, not revenue." />
      <FilterBar label="Estimate filters">
        <FormField label="Status" className="w-56">
          <Select value={status} onChange={(e) => go({ status: e.target.value, page: 1 })}>
            <option value="">All statuses</option>
            {STATUSES.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </Select>
        </FormField>
      </FilterBar>
      <DataTable
        caption="Estimates"
        columns={columns}
        rows={q.data?.items}
        rowKey={(e) => e.id}
        loading={q.isLoading}
        error={q.error}
        onRetry={() => void q.refetch()}
        page={q.data?.page ?? page}
        pageSize={PAGE_SIZE}
        total={q.data?.total}
        onPageChange={(p) => go({ page: p })}
        empty={<EmptyState title="No estimates" description={status ? "No estimate has this status." : "Estimates appear once a dispatcher drafts one on a request."} />}
      />
    </>
  );
}
