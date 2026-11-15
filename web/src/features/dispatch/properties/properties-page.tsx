"use client";

import { Pencil, Plus, Search } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { Badge, Button, DataTable, EmptyState, FilterBar, FormField, Input, PageHeader, Select } from "@/components/ui";
import type { Column } from "@/components/ui";
import type { Page, Schemas } from "@/lib/api/types";
import { useRole } from "@/lib/auth";
import { useApiQuery } from "@/lib/query/hooks";
import { qk } from "@/lib/query/keys";
import { PropertyFormDialog } from "./forms";

type Property = Schemas["PropertyOut"];
const PAGE_SIZE = 20;

export function PropertiesPage() {
  const router = useRouter();
  const pathname = usePathname();
  const sp = useSearchParams();
  const role = useRole();
  const q = sp.get("q") ?? "";
  const active = sp.get("active") ?? "";
  const page = Math.max(1, Number(sp.get("page") ?? "1") || 1);
  const [draft, setDraft] = useState<string | null>(null);
  const [editing, setEditing] = useState<Property | "new" | null>(null);
  const params = { q: q || undefined, is_active: active === "" ? undefined : active === "true", page, page_size: PAGE_SIZE };
  const list = useApiQuery<Page<Property>>({ queryKey: (o) => qk.properties.list(o, params), path: "/properties", query: params, placeholderData: (p) => p });

  function go(next: { q?: string; active?: string; page?: number }) {
    const n = new URLSearchParams();
    const nq = next.q ?? q;
    const na = next.active ?? active;
    const np = next.page ?? 1;
    if (nq) n.set("q", nq);
    if (na) n.set("active", na);
    if (np > 1) n.set("page", String(np));
    const qs = n.toString();
    router.replace(qs ? `${pathname}?${qs}` : pathname);
  }

  const canEdit = role === "DISPATCHER" || role === "ADMIN";
  const columns: Column<Property>[] = [
    {
      key: "name",
      header: "Property",
      className: "min-w-48",
      cell: (p) => (
        <Link href={`/properties/${p.id}`} className="font-semibold text-primary-dark hover:underline">
          {p.name}
        </Link>
      ),
    },
    { key: "address", header: "Address", cell: (p) => p.address },
    { key: "status", header: "Status", cell: (p) => (p.is_active ? <Badge tone="success">Active</Badge> : <Badge>Inactive</Badge>) },
    {
      key: "act",
      header: <span className="sr-only">Actions</span>,
      cell: (p) =>
        canEdit && (
          <Button size="sm" variant="ghost" aria-label={`Edit ${p.name}`} onClick={() => setEditing(p)}>
            <Pencil className="size-4" aria-hidden /> Edit
          </Button>
        ),
    },
  ];

  return (
    <>
      <PageHeader
        title="Properties and assets"
        description="Sites, the equipment in them, and who may request work there."
        actions={
          canEdit && (
            <Button onClick={() => setEditing("new")}>
              <Plus className="size-4" aria-hidden /> New property
            </Button>
          )
        }
      />
      <FilterBar label="Property filters">
        <form
          role="search"
          aria-label="Search properties"
          className="flex min-w-60 flex-1 items-end gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            go({ q: (draft ?? q).trim(), page: 1 });
            setDraft(null);
          }}
        >
          <FormField label="Search" className="flex-1">
            <Input type="search" placeholder="Name or address" value={draft ?? q} onChange={(e) => setDraft(e.target.value)} />
          </FormField>
          <Button type="submit" variant="secondary" aria-label="Search">
            <Search className="size-4" aria-hidden />
          </Button>
        </form>
        <FormField label="Status" className="w-44">
          <Select value={active} onChange={(e) => go({ active: e.target.value, page: 1 })}>
            <option value="">All</option>
            <option value="true">Active</option>
            <option value="false">Inactive</option>
          </Select>
        </FormField>
      </FilterBar>
      <DataTable
        caption="Properties"
        columns={columns}
        rows={list.data?.items}
        rowKey={(p) => p.id}
        loading={list.isLoading}
        error={list.error}
        onRetry={() => void list.refetch()}
        page={list.data?.page ?? page}
        pageSize={PAGE_SIZE}
        total={list.data?.total}
        onPageChange={(p) => go({ page: p })}
        empty={<EmptyState title="No properties found" />}
      />
      <PropertyFormDialog open={editing !== null} onOpenChange={(o) => !o && setEditing(null)} property={editing && editing !== "new" ? editing : undefined} />
    </>
  );
}
