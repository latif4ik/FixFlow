"use client";

import { Pencil, Plus, UserMinus, UserPlus } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { Badge, Button, ConfirmDialog, DataTable, DateTime, EmptyState, ErrorState, FormField, LoadingState, PageHeader, Panel, Select } from "@/components/ui";
import type { Column } from "@/components/ui";
import type { Page, Schemas } from "@/lib/api/types";
import { useApiMutation, useApiQuery } from "@/lib/query/hooks";
import { qk } from "@/lib/query/keys";
import { AssetFormDialog, PropertyFormDialog } from "./forms";

type Property = Schemas["PropertyOut"];
type Asset = Schemas["AssetOut"];
type Access = Schemas["AccessOut"];
type Member = Schemas["MemberOut"];

const ASSET_STATUS: Record<Asset["status"], { label: string; tone: "success" | "warning" | "neutral" }> = {
  ACTIVE: { label: "Active", tone: "success" },
  OUT_OF_SERVICE: { label: "Out of service", tone: "warning" },
  RETIRED: { label: "Retired", tone: "neutral" },
};

/** "Who can request here": grants for requesters (REQUESTER members) on this property. */
export function AccessPanel({ propertyId }: { propertyId: string }) {
  const [revoke, setRevoke] = useState<Access | null>(null);
  const [pick, setPick] = useState("");
  const list = useApiQuery<Page<Access>>({
    queryKey: (o) => qk.properties.access(o, propertyId),
    path: `/properties/${propertyId}/access`,
    query: { page_size: 100 },
  });
  const members = useApiQuery<Page<Member>>({
    queryKey: (o) => qk.members.list(o, { role: "REQUESTER", is_active: true, page_size: 100 }),
    path: "/org/members",
    query: { role: "REQUESTER", is_active: true, page_size: 100 },
    staleTime: 60_000,
  });
  const invalidate = (o: string) => [qk.properties.access(o, propertyId)];
  const grant = useApiMutation<unknown, { membership_id: string }>({
    request: (v) => ({ path: `/properties/${propertyId}/access`, body: v }),
    idempotent: true,
    invalidate,
    successMessage: "Access granted.",
    onSuccess: () => setPick(""),
  });
  const del = useApiMutation<unknown, { membership_id: string }>({
    request: (v) => ({ method: "DELETE", path: `/properties/${propertyId}/access/${v.membership_id}` }),
    invalidate,
    successMessage: "Access revoked.",
  });
  const granted = new Set((list.data?.items ?? []).map((a) => a.membership_id));
  const candidates = (members.data?.items ?? []).filter((m) => !granted.has(m.membership_id));

  return (
    <Panel title="Who can request here" bodyClassName="flex flex-col gap-4">
      <p className="text-[13px] text-muted">Requesters can only submit requests for properties they have been granted, and only see their own requests.</p>
      {list.isLoading ? (
        <LoadingState label="Loading access" />
      ) : list.error ? (
        <ErrorState error={list.error} onRetry={() => void list.refetch()} />
      ) : list.data && list.data.items.length === 0 ? (
        <p className="text-sm text-muted">No requester has access to this property yet.</p>
      ) : (
        <ul aria-label="Requesters with access" className="flex flex-col">
          {list.data?.items.map((a) => (
            <li key={a.membership_id} className="flex flex-wrap items-center justify-between gap-2 border-t border-border py-2.5 first:border-t-0">
              <span className="flex min-w-0 flex-col">
                <span className="font-semibold text-ink">{a.full_name}</span>
                <span className="truncate text-[13px] text-muted">
                  {a.email} · granted <DateTime value={a.created_at} style="date" />
                </span>
              </span>
              <Button size="sm" variant="secondary" aria-label={`Revoke access for ${a.full_name}`} onClick={() => setRevoke(a)}>
                <UserMinus className="size-4" aria-hidden /> Revoke
              </Button>
            </li>
          ))}
        </ul>
      )}
      <form
        aria-label="Grant access"
        className="flex flex-wrap items-end gap-2 border-t border-border pt-4"
        onSubmit={(e) => {
          e.preventDefault();
          if (pick) grant.mutate({ membership_id: pick });
        }}
      >
        <FormField label="Grant access to a requester" className="min-w-56 flex-1">
          <Select value={pick} onChange={(e) => setPick(e.target.value)}>
            <option value="">Choose a requester</option>
            {candidates.map((m) => (
              <option key={m.membership_id} value={m.membership_id}>
                {m.full_name} ({m.email})
              </option>
            ))}
          </Select>
        </FormField>
        <Button type="submit" disabled={!pick} loading={grant.isPending}>
          <UserPlus className="size-4" aria-hidden /> Grant access
        </Button>
      </form>
      <ConfirmDialog
        open={revoke !== null}
        onOpenChange={(o) => !o && setRevoke(null)}
        title={`Revoke access for ${revoke?.full_name ?? ""}?`}
        description="They will no longer be able to submit requests for this property. Their existing requests stay visible to them."
        confirmLabel="Revoke access"
        cancelLabel="Keep access"
        onConfirm={() => del.mutateAsync({ membership_id: revoke!.membership_id })}
      />
    </Panel>
  );
}

export function PropertyDetailPage({ propertyId }: { propertyId: string }) {
  const [editing, setEditing] = useState(false);
  const [adding, setAdding] = useState(false);
  const p = useApiQuery<Property>({ queryKey: (o) => qk.properties.detail(o, propertyId), path: `/properties/${propertyId}` });
  const assets = useApiQuery<Page<Asset>>({
    queryKey: (o) => qk.assets.list(o, { property_id: propertyId, page_size: 100 }),
    path: "/assets",
    query: { property_id: propertyId, page_size: 100 },
  });

  if (p.isLoading) return <LoadingState label="Loading property" />;
  if (p.error) return <ErrorState title="Could not load the property" error={p.error} onRetry={() => void p.refetch()} />;
  if (!p.data) return null;
  const d = p.data;

  const columns: Column<Asset>[] = [
    {
      key: "code",
      header: "Asset",
      cell: (a) => (
        <Link href={`/assets/${a.id}`} className="font-semibold text-primary-dark hover:underline">
          {a.code}
        </Link>
      ),
    },
    { key: "name", header: "Name", cell: (a) => a.name },
    { key: "type", header: "Type", cell: (a) => a.asset_type },
    { key: "status", header: "Status", cell: (a) => <Badge tone={ASSET_STATUS[a.status].tone}>{ASSET_STATUS[a.status].label}</Badge> },
  ];

  return (
    <>
      <PageHeader
        breadcrumb={[{ label: "Properties and assets", href: "/properties" }, { label: d.name }]}
        title={d.name}
        description={d.address}
        actions={
          <Button variant="secondary" onClick={() => setEditing(true)}>
            <Pencil className="size-4" aria-hidden /> Edit property
          </Button>
        }
      />
      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_380px]">
        <div className="flex min-w-0 flex-col gap-5">
          <Panel title="Details">
            <dl className="grid gap-4 sm:grid-cols-2">
              <div>
                <dt className="text-xs text-muted">Status</dt>
                <dd className="font-medium">{d.is_active ? <Badge tone="success">Active</Badge> : <Badge>Inactive</Badge>}</dd>
              </div>
              <div>
                <dt className="text-xs text-muted">Address</dt>
                <dd className="font-medium">{d.address}</dd>
              </div>
              <div className="sm:col-span-2">
                <dt className="text-xs text-muted">Access and contact instructions</dt>
                <dd className="font-medium">{d.contact_instructions ?? <span className="text-muted">None</span>}</dd>
              </div>
            </dl>
          </Panel>
          <Panel
            title="Assets"
            actions={
              <Button size="sm" onClick={() => setAdding(true)}>
                <Plus className="size-4" aria-hidden /> Add asset
              </Button>
            }
            bodyClassName="p-0"
          >
            <DataTable caption={`Assets in ${d.name}`} columns={columns} rows={assets.data?.items} rowKey={(a) => a.id} loading={assets.isLoading} error={assets.error} onRetry={() => void assets.refetch()} empty={<EmptyState title="No assets in this property yet" />} />
          </Panel>
        </div>
        <aside className="flex min-w-0 flex-col gap-5" aria-label="Property side panels">
          <AccessPanel propertyId={propertyId} />
        </aside>
      </div>
      <PropertyFormDialog open={editing} onOpenChange={setEditing} property={d} />
      <AssetFormDialog open={adding} onOpenChange={setAdding} propertyId={propertyId} />
    </>
  );
}
