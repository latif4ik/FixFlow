"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Plus, UserCheck, UserX } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { Badge, Button, ConfirmDialog, DataTable, Dialog, FilterBar, FormField, FormServerError, Input, Label, Select } from "@/components/ui";
import type { Column } from "@/components/ui";
import type { Page, Role, Schemas } from "@/lib/api";
import { ROLE_LABEL } from "@/lib/nav";
import { qk, useApiMutation, useApiQuery } from "@/lib/query";
import { ActionError, AdminPage } from "./shared";

type Member = Schemas["MemberOut"];
const ROLES: Role[] = ["ADMIN", "DISPATCHER", "TECHNICIAN", "REQUESTER"];
const PAGE_SIZE = 20;

const addSchema = z.object({
  email: z.string().trim().email("Enter a valid email address."),
  full_name: z.string().trim().min(2, "Enter the full name.").max(120, "At most 120 characters."),
  role: z.enum(["ADMIN", "DISPATCHER", "TECHNICIAN", "REQUESTER"]),
  password: z.string().refine((v) => v === "" || v.length >= 8, "At least 8 characters, or leave empty for an existing user."),
});
type AddForm = z.infer<typeof addSchema>;

function AddMemberDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const form = useForm<AddForm>({ resolver: zodResolver(addSchema), defaultValues: { email: "", full_name: "", role: "TECHNICIAN", password: "" } });
  const add = useApiMutation<Member, AddForm>({
    request: (v) => ({ path: "/org/members", body: { ...v, password: v.password || null } }),
    idempotent: true,
    invalidate: (o) => [qk.members.all(o), qk.technicians.all(o)],
    successMessage: "Member added.",
    form,
    onSuccess: () => {
      form.reset();
      onOpenChange(false);
    },
  });
  return (
    <Dialog open={open} onOpenChange={onOpenChange} title="Add a member" description="Add an existing user by email, or create a new account with an initial password.">
      <form onSubmit={form.handleSubmit((v) => add.mutate(v))} noValidate className="flex flex-col gap-4">
        <FormField label="Email" error={form.formState.errors.email?.message} required>
          <Input type="email" autoComplete="off" {...form.register("email")} />
        </FormField>
        <FormField label="Full name" error={form.formState.errors.full_name?.message} required>
          <Input autoComplete="off" {...form.register("full_name")} />
        </FormField>
        <FormField label="Role" error={form.formState.errors.role?.message} required>
          <Select {...form.register("role")}>
            {ROLES.map((r) => (
              <option key={r} value={r}>
                {ROLE_LABEL[r]}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField label="Initial password" hint="Only needed when the person has no account yet. At least 8 characters." error={form.formState.errors.password?.message}>
          <Input type="password" autoComplete="new-password" {...form.register("password")} />
        </FormField>
        <FormServerError form={form} />
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button type="submit" loading={add.isPending}>
            Add member
          </Button>
        </div>
      </form>
    </Dialog>
  );
}

export function StaffPage() {
  const [role, setRole] = useState("");
  const [active, setActive] = useState("");
  const [search, setSearch] = useState("");
  const [applied, setApplied] = useState("");
  const [page, setPage] = useState(1);
  const [adding, setAdding] = useState(false);
  const [target, setTarget] = useState<Member | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const params = { role: role || undefined, is_active: active === "" ? undefined : active === "true", q: applied || undefined, page, page_size: PAGE_SIZE };
  const q = useApiQuery<Page<Member>>({ queryKey: (o) => qk.members.list(o, params), path: "/org/members", query: params });

  const patch = useApiMutation<Member, { id: string; body: { role?: Role; is_active?: boolean } }>({
    request: (v) => ({ method: "PATCH", path: `/org/members/${v.id}`, body: v.body }),
    invalidate: (o) => [qk.members.all(o), qk.technicians.all(o)],
    errorMessage: false,
    onSuccess: () => setActionError(null),
    onError: (e) => setActionError(e.message),
    successMessage: (m) => `${m.full_name} updated.`,
  });

  const columns: Column<Member>[] = [
    {
      key: "name",
      header: "Name",
      cell: (m) => (
        <span className="flex flex-col">
          <strong className="text-ink">{m.full_name}</strong>
          <span className="text-[13px] text-muted">{m.email}</span>
        </span>
      ),
    },
    {
      key: "role",
      header: "Role",
      cell: (m) => (
        <Select
          aria-label={`Role for ${m.full_name}`}
          value={m.role}
          className="h-9 w-40"
          disabled={patch.isPending}
          onChange={(e) => {
            setActionError(null);
            patch.mutate({ id: m.membership_id, body: { role: e.target.value as Role } });
          }}
        >
          {ROLES.map((r) => (
            <option key={r} value={r}>
              {ROLE_LABEL[r]}
            </option>
          ))}
        </Select>
      ),
    },
    {
      key: "active",
      header: "Status",
      cell: (m) => (m.is_active ? <Badge tone="success" icon={UserCheck}>Active</Badge> : <Badge tone="neutral" icon={UserX}>Deactivated</Badge>),
    },
    {
      key: "actions",
      header: <span className="sr-only">Actions</span>,
      className: "text-right",
      cell: (m) =>
        m.is_active ? (
          <Button
            size="sm"
            variant="secondary"
            onClick={() => {
              setActionError(null);
              setTarget(m);
            }}
          >
            Deactivate <span className="sr-only">{m.full_name}</span>
          </Button>
        ) : (
          <Button size="sm" variant="secondary" loading={patch.isPending} onClick={() => patch.mutate({ id: m.membership_id, body: { is_active: true } })}>
            Activate <span className="sr-only">{m.full_name}</span>
          </Button>
        ),
    },
  ];

  return (
    <AdminPage
      title="Staff"
      description="Members of this organization and their roles. Roles apply only inside this organization."
      actions={
        <Button onClick={() => setAdding(true)}>
          <Plus className="size-4" aria-hidden /> Add member
        </Button>
      }
    >
      <FilterBar label="Member filters">
        <form
          className="flex flex-col gap-1.5"
          onSubmit={(e) => {
            e.preventDefault();
            setApplied(search.trim());
            setPage(1);
          }}
        >
          <Label htmlFor="staff-q">Search</Label>
          <div className="flex gap-2">
            <Input id="staff-q" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Name or email" className="w-56" />
            <Button type="submit" variant="secondary">
              Search
            </Button>
          </div>
        </form>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="staff-role">Role</Label>
          <Select
            id="staff-role"
            value={role}
            onChange={(e) => {
              setRole(e.target.value);
              setPage(1);
            }}
            className="w-44"
          >
            <option value="">All roles</option>
            {ROLES.map((r) => (
              <option key={r} value={r}>
                {ROLE_LABEL[r]}
              </option>
            ))}
          </Select>
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="staff-active">Status</Label>
          <Select
            id="staff-active"
            value={active}
            onChange={(e) => {
              setActive(e.target.value);
              setPage(1);
            }}
            className="w-40"
          >
            <option value="">Any status</option>
            <option value="true">Active</option>
            <option value="false">Deactivated</option>
          </Select>
        </div>
      </FilterBar>
      <ActionError message={target ? null : actionError} />
      <DataTable
        caption="Members"
        columns={columns}
        rows={q.data?.items}
        rowKey={(m) => m.membership_id}
        loading={q.isLoading}
        error={q.error}
        onRetry={() => q.refetch()}
        page={page}
        pageSize={PAGE_SIZE}
        total={q.data?.total ?? 0}
        onPageChange={setPage}
      />
      <AddMemberDialog open={adding} onOpenChange={setAdding} />
      <ConfirmDialog
        open={target !== null}
        onOpenChange={(o) => {
          if (!o) {
            setTarget(null);
            setActionError(null);
          }
        }}
        title={target ? `Deactivate ${target.full_name}?` : "Deactivate member"}
        description={
          <span className="flex flex-col gap-2">
            <span>They will lose access to this organization immediately. Their history is kept and you can activate them again.</span>
            <ActionError message={actionError} />
          </span>
        }
        confirmLabel="Deactivate"
        onConfirm={() => patch.mutateAsync({ id: target!.membership_id, body: { is_active: false } })}
      />
    </AdminPage>
  );
}
