"use client";

import { Paperclip, Pencil } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { Badge, Button, ConfirmDialog, DataTable, DateTime, EmptyState, ErrorState, FormField, LoadingState, Money, PageHeader, Panel, PriorityBadge, Select, StatusBadge } from "@/components/ui";
import type { Column } from "@/components/ui";
import type { Page, Schemas } from "@/lib/api/types";
import { useApiMutation, useApiQuery } from "@/lib/query/hooks";
import { qk } from "@/lib/query/keys";
import { AssetFormDialog } from "./forms";

type AssetDetail = Schemas["AssetDetail"];
type History = Schemas["AssetHistoryItem"];
type Status = AssetDetail["status"];

const STATUS: Record<Status, { label: string; tone: "success" | "warning" | "neutral" }> = {
  ACTIVE: { label: "Active", tone: "success" },
  OUT_OF_SERVICE: { label: "Out of service", tone: "warning" },
  RETIRED: { label: "Retired", tone: "neutral" },
};
const HISTORY_PAGE = 10;

function StatusChanger({ asset }: { asset: AssetDetail }) {
  const [next, setNext] = useState<Status>(asset.status);
  const [confirm, setConfirm] = useState(false);
  const m = useApiMutation<unknown, Status>({
    request: (status) => ({ method: "PATCH", path: `/assets/${asset.id}`, body: { status } }),
    invalidate: (o) => [qk.assets.all(o)],
    successMessage: "Asset status updated.",
  });
  return (
    <form
      aria-label="Change asset status"
      className="flex flex-wrap items-end gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        if (next === asset.status) return;
        if (next === "RETIRED") setConfirm(true);
        else m.mutate(next);
      }}
    >
      <FormField label="Status" className="w-48">
        <Select value={next} onChange={(e) => setNext(e.target.value as Status)}>
          {(Object.keys(STATUS) as Status[]).map((s) => (
            <option key={s} value={s}>
              {STATUS[s].label}
            </option>
          ))}
        </Select>
      </FormField>
      <Button type="submit" variant="secondary" disabled={next === asset.status} loading={m.isPending}>
        Change status
      </Button>
      <ConfirmDialog
        open={confirm}
        onOpenChange={setConfirm}
        title={`Retire ${asset.code}?`}
        description="Retired assets can no longer be selected on new requests. Existing history is kept."
        confirmLabel="Retire asset"
        onConfirm={() => m.mutateAsync("RETIRED")}
      />
    </form>
  );
}

export function AssetDetailPage({ assetId }: { assetId: string }) {
  const [editing, setEditing] = useState(false);
  const [page, setPage] = useState(1);
  const a = useApiQuery<AssetDetail>({ queryKey: (o) => qk.assets.detail(o, assetId), path: `/assets/${assetId}` });
  const hp = { page, page_size: HISTORY_PAGE };
  const h = useApiQuery<Page<History>>({ queryKey: (o) => qk.assets.history(o, assetId, hp), path: `/assets/${assetId}/history`, query: hp, placeholderData: (p) => p });

  if (a.isLoading) return <LoadingState label="Loading asset" />;
  if (a.error) return <ErrorState title="Could not load the asset" error={a.error} onRetry={() => void a.refetch()} />;
  if (!a.data) return null;
  const d = a.data;

  const columns: Column<History>[] = [
    {
      key: "req",
      header: "Request",
      className: "min-w-52",
      cell: (r) => (
        <Link href={`/requests/${r.request_id}`} className="font-medium hover:underline">
          <span className="font-semibold text-primary-dark">{r.display_id}</span> · {r.title}
        </Link>
      ),
    },
    { key: "status", header: "Outcome", cell: (r) => <StatusBadge status={r.outcome.status} /> },
    { key: "priority", header: "Priority", cell: (r) => <PriorityBadge priority={r.priority} /> },
    { key: "tech", header: "Technician", cell: (r) => r.technician?.name.replace(/ \(.*\)$/, "") ?? <span className="text-muted">Unassigned</span> },
    { key: "created", header: "Opened", cell: (r) => <DateTime value={r.created_at} style="date" /> },
    { key: "done", header: "Completed", cell: (r) => (r.completed_at ? <DateTime value={r.completed_at} style="date" /> : <span className="text-muted">-</span>) },
    {
      key: "mat",
      header: "Materials",
      cell: (r) =>
        r.materials.items.length === 0 ? (
          <span className="text-muted">None</span>
        ) : (
          <span>
            {r.materials.items.length} item{r.materials.items.length === 1 ? "" : "s"} · <Money minor={r.materials.total_cost_minor} />
          </span>
        ),
    },
    {
      key: "att",
      header: "Files",
      cell: (r) => (
        <span className="inline-flex items-center gap-1 text-muted">
          <Paperclip className="size-3.5" aria-hidden />
          {r.attachment_count}
        </span>
      ),
    },
  ];

  return (
    <>
      <PageHeader
        breadcrumb={[{ label: "Properties and assets", href: "/properties" }, { label: "Property", href: `/properties/${d.property_id}` }, { label: d.code }]}
        title={
          <span className="flex flex-col gap-1">
            <span className="text-sm font-semibold text-muted">{d.code}</span>
            {d.name}
          </span>
        }
        actions={
          <Button variant="secondary" onClick={() => setEditing(true)}>
            <Pencil className="size-4" aria-hidden /> Edit asset
          </Button>
        }
      />
      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_380px]">
        <div className="flex min-w-0 flex-col gap-5">
          <Panel title="Asset facts">
            <dl className="grid gap-4 sm:grid-cols-2">
              <div>
                <dt className="text-xs text-muted">Status</dt>
                <dd>
                  <Badge tone={STATUS[d.status].tone}>{STATUS[d.status].label}</Badge>
                </dd>
              </div>
              <div>
                <dt className="text-xs text-muted">Type</dt>
                <dd className="font-medium">{d.asset_type}</dd>
              </div>
              <div>
                <dt className="text-xs text-muted">Serial number</dt>
                <dd className="font-medium">{d.serial_number ?? "-"}</dd>
              </div>
              <div>
                <dt className="text-xs text-muted">Installed</dt>
                <dd className="font-medium">{d.installed_on ? <DateTime value={`${d.installed_on}T12:00:00Z`} style="date" tz="UTC" /> : "-"}</dd>
              </div>
              {d.notes && (
                <div className="sm:col-span-2">
                  <dt className="text-xs text-muted">Notes</dt>
                  <dd className="font-medium">{d.notes}</dd>
                </div>
              )}
            </dl>
          </Panel>
          <Panel title="Service history" bodyClassName="p-0">
            <DataTable
              caption="Asset history"
              columns={columns}
              rows={h.data?.items}
              rowKey={(r) => r.request_id}
              loading={h.isLoading}
              error={h.error}
              onRetry={() => void h.refetch()}
              page={h.data?.page ?? page}
              pageSize={HISTORY_PAGE}
              total={h.data?.total}
              onPageChange={setPage}
              empty={<EmptyState title="No requests have been filed for this asset" />}
            />
          </Panel>
        </div>
        <aside className="flex min-w-0 flex-col gap-5" aria-label="Asset side panels">
          <Panel title="Status" bodyClassName="flex flex-col gap-3">
            <StatusChanger key={d.status} asset={d} />
          </Panel>
          <Panel title="Open work" bodyClassName="flex flex-col gap-2">
            {d.open_work.length === 0 ? (
              <p className="text-sm text-muted">No open requests.</p>
            ) : (
              <ul className="flex flex-col">
                {d.open_work.map((w) => (
                  <li key={w.id} className="flex flex-col gap-1 border-t border-border py-2 first:border-t-0">
                    <Link href={`/requests/${w.id}`} className="text-sm font-medium hover:underline">
                      <span className="font-semibold text-primary-dark">{w.display_id}</span> · {w.title}
                    </Link>
                    <span className="flex flex-wrap gap-1.5">
                      <StatusBadge status={w.status} />
                      <PriorityBadge priority={w.priority} />
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </Panel>
          <Panel title="Last completed service">
            {d.last_completed_service ? (
              <p className="text-sm">
                <Link href={`/requests/${d.last_completed_service.request.id}`} className="font-semibold text-primary-dark hover:underline">
                  {d.last_completed_service.request.display_id}
                </Link>{" "}
                {d.last_completed_service.request.title}
                <span className="mt-1 block text-muted">
                  <DateTime value={d.last_completed_service.completed_at} style="date" />
                  {d.last_completed_service.technician ? ` by ${d.last_completed_service.technician.name.replace(/ \(.*\)$/, "")}` : ""}
                </span>
              </p>
            ) : (
              <p className="text-sm text-muted">No completed service yet.</p>
            )}
          </Panel>
          <Panel title="Next scheduled maintenance">
            {d.next_maintenance ? (
              <p className="text-sm">
                <span className="font-semibold">{d.next_maintenance.title}</span>
                <span className="block text-muted">
                  Due <DateTime value={`${d.next_maintenance.date}T12:00:00Z`} style="date" tz="UTC" />
                </span>
              </p>
            ) : (
              <p className="text-sm text-muted">No maintenance plan is scheduled for this asset.</p>
            )}
          </Panel>
        </aside>
      </div>
      <AssetFormDialog open={editing} onOpenChange={setEditing} propertyId={d.property_id} asset={d} />
    </>
  );
}
