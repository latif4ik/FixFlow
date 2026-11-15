"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Trash2 } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { Badge, Button, Checkbox, ConfirmDialog, DataTable, DateTime, Dialog, ErrorState, FormField, FormServerError, IconButton, Input, Label, Panel, Skeleton } from "@/components/ui";
import type { Column } from "@/components/ui";
import type { Page, Schemas } from "@/lib/api";
import { useOrgTimezone } from "@/lib/auth";
import { qk, useApiMutation, useApiQuery } from "@/lib/query";
import { zonedInstant } from "@/features/dashboard/tz";
import { AdminPage, hhmm, withSeconds } from "./shared";
import { WeekEditor } from "./week-editor";
import type { DayInterval } from "./week-editor";

type Tech = Schemas["TechnicianOut"];
type Skill = Schemas["SkillOut"];
type TimeOff = Schemas["TimeOffOut"];

function SkillsEditor({ tech, skills }: { tech: Tech; skills: Skill[] }) {
  const [selected, setSelected] = useState<string[]>(tech.skills.map((s) => s.id));
  const save = useApiMutation<Tech, string[]>({
    request: (ids) => ({ method: "PUT", path: `/technicians/${tech.membership_id}/skills`, body: { skill_ids: ids } }),
    invalidate: (o) => [qk.technicians.all(o)],
    successMessage: "Skills saved.",
  });
  return (
    <form
      aria-label="Technician skills"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate(selected);
      }}
      className="flex flex-col gap-3"
    >
      {skills.length === 0 && <p className="text-sm text-muted">No skills defined yet. Add them under Categories and skills.</p>}
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        {skills.map((s) => (
          <div key={s.id} className="flex items-center gap-2">
            <Checkbox id={`tskill-${s.id}`} checked={selected.includes(s.id)} onCheckedChange={(c) => setSelected((cur) => (c === true ? [...cur, s.id] : cur.filter((x) => x !== s.id)))} />
            <Label htmlFor={`tskill-${s.id}`} className="font-normal">
              {s.name}
            </Label>
          </div>
        ))}
      </div>
      <div>
        <Button type="submit" loading={save.isPending}>
          Save skills
        </Button>
      </div>
    </form>
  );
}

const toLocalInstant = (v: string, tz: string) => {
  const [d, t] = v.split("T") as [string, string];
  const [hh, mm] = t.split(":").map(Number) as [number, number];
  return zonedInstant(d, hh, mm, tz);
};

const timeOffSchema = z
  .object({ start: z.string().min(1, "Choose a start."), end: z.string().min(1, "Choose an end."), reason: z.string().max(200, "At most 200 characters.") })
  .refine((v) => !v.start || !v.end || v.end > v.start, { path: ["end"], message: "The end must be after the start." });
type TimeOffForm = z.infer<typeof timeOffSchema>;

function TimeOffEditor({ tech }: { tech: Tech }) {
  const tz = useOrgTimezone();
  const form = useForm<TimeOffForm>({ resolver: zodResolver(timeOffSchema), defaultValues: { start: "", end: "", reason: "" } });
  const add = useApiMutation<TimeOff, TimeOffForm>({
    request: (v) => ({
      path: `/technicians/${tech.membership_id}/time-off`,
      body: { start_at: new Date(toLocalInstant(v.start, tz)).toISOString(), end_at: new Date(toLocalInstant(v.end, tz)).toISOString(), reason: v.reason.trim() || null },
    }),
    idempotent: true,
    invalidate: (o) => [qk.technicians.all(o)],
    successMessage: "Time off added.",
    form,
    onSuccess: () => form.reset(),
  });
  const del = useApiMutation<unknown, string>({
    request: (id) => ({ method: "DELETE", path: `/technicians/${tech.membership_id}/time-off/${id}` }),
    invalidate: (o) => [qk.technicians.all(o)],
    successMessage: "Time off removed.",
  });
  const [toDelete, setToDelete] = useState<TimeOff | null>(null);
  return (
    <div className="flex flex-col gap-4">
      <form onSubmit={form.handleSubmit((v) => add.mutate(v))} noValidate aria-label="Add time off" className="flex flex-wrap items-start gap-3">
        <FormField label={`Starts (${tz})`} error={form.formState.errors.start?.message} required>
          <Input type="datetime-local" {...form.register("start")} className="w-56" />
        </FormField>
        <FormField label={`Ends (${tz})`} error={form.formState.errors.end?.message} required>
          <Input type="datetime-local" {...form.register("end")} className="w-56" />
        </FormField>
        <FormField label="Reason" error={form.formState.errors.reason?.message}>
          <Input {...form.register("reason")} className="w-56" />
        </FormField>
        <div className="pt-[26px]">
          <Button type="submit" loading={add.isPending}>
            Add time off
          </Button>
        </div>
        <div className="w-full">
          <FormServerError form={form} />
        </div>
      </form>
      {tech.time_off.length === 0 ? (
        <p className="text-sm text-muted">No time off recorded.</p>
      ) : (
        <ul className="divide-y divide-border">
          {tech.time_off.map((t) => (
            <li key={t.id} className="flex items-center justify-between gap-3 py-2 text-sm">
              <span>
                <DateTime value={t.start_at} /> to <DateTime value={t.end_at} />
                {t.reason && <span className="text-muted"> · {t.reason}</span>}
              </span>
              <IconButton aria-label="Remove time off" variant="ghost" icon={<Trash2 className="size-4" aria-hidden />} onClick={() => setToDelete(t)} />
            </li>
          ))}
        </ul>
      )}
      <ConfirmDialog
        open={toDelete !== null}
        onOpenChange={(o) => !o && setToDelete(null)}
        title="Remove this time off?"
        description="The technician becomes available again in that period."
        confirmLabel="Remove"
        onConfirm={() => del.mutateAsync(toDelete!.id)}
      />
    </div>
  );
}

function AvailabilityEditor({ tech }: { tech: Tech }) {
  const save = useApiMutation<Tech, DayInterval[]>({
    request: (v) => ({ method: "PUT", path: `/technicians/${tech.membership_id}/availability`, body: { intervals: v.map((i) => ({ weekday: i.weekday, start_time: withSeconds(i.start), end_time: withSeconds(i.end) })) } }),
    invalidate: (o) => [qk.technicians.all(o), qk.schedule.all(o), qk.reports.all(o)],
    successMessage: "Availability saved.",
  });
  return (
    <WeekEditor
      key={JSON.stringify(tech.availability)}
      idPrefix="Availability"
      closedLabel="Unavailable"
      initial={tech.availability.map((a) => ({ weekday: a.weekday, start: hhmm(a.start_time), end: hhmm(a.end_time) }))}
      saving={save.isPending}
      saveLabel="Save availability"
      onSave={(v) => save.mutateAsync(v).catch(() => undefined)}
    />
  );
}

function TechnicianDialog({ id, onClose }: { id: string; onClose: () => void }) {
  const q = useApiQuery<Tech>({ queryKey: (o) => qk.technicians.detail(o, id), path: `/technicians/${id}` });
  const skills = useApiQuery<Page<Skill>>({ queryKey: (o) => qk.skills.list(o, { all: true }), path: "/skills", query: { page_size: 100 } });
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()} title={q.data?.full_name ?? "Technician"} description={q.data?.email} className="max-w-3xl">
      {q.error ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : !q.data ? (
        <Skeleton className="h-48 w-full" />
      ) : (
        <div className="flex flex-col gap-6">
          <section aria-labelledby="t-skills">
            <h3 id="t-skills" className="mb-2 font-heading text-base font-bold">
              Skills
            </h3>
            <SkillsEditor key={q.data.skills.map((s) => s.id).join()} tech={q.data} skills={skills.data?.items ?? []} />
          </section>
          <section aria-labelledby="t-avail">
            <h3 id="t-avail" className="mb-2 font-heading text-base font-bold">
              Weekly availability
            </h3>
            <AvailabilityEditor tech={q.data} />
          </section>
          <section aria-labelledby="t-off">
            <h3 id="t-off" className="mb-2 font-heading text-base font-bold">
              Time off
            </h3>
            <TimeOffEditor tech={q.data} />
          </section>
        </div>
      )}
    </Dialog>
  );
}

export function TechniciansPage() {
  const [page, setPage] = useState(1);
  const [open, setOpen] = useState<string | null>(null);
  const params = { page, page_size: 20 };
  const q = useApiQuery<Page<Tech>>({ queryKey: (o) => qk.technicians.list(o, params), path: "/technicians", query: params });
  const columns: Column<Tech>[] = [
    {
      key: "name",
      header: "Technician",
      cell: (t) => (
        <span className="flex flex-col">
          <strong className="text-ink">{t.full_name}</strong>
          <span className="text-[13px] text-muted">{t.email}</span>
        </span>
      ),
    },
    { key: "skills", header: "Skills", cell: (t) => (t.skills.length ? <span className="flex flex-wrap gap-1">{t.skills.map((s) => <Badge key={s.id}>{s.name}</Badge>)}</span> : <span className="text-muted">None</span>) },
    { key: "active", header: "Status", cell: (t) => (t.is_active ? <Badge tone="success">Active</Badge> : <Badge>Deactivated</Badge>) },
    {
      key: "actions",
      header: <span className="sr-only">Actions</span>,
      className: "text-right",
      cell: (t) => (
        <Button size="sm" variant="secondary" onClick={() => setOpen(t.membership_id)}>
          Manage <span className="sr-only">{t.full_name}</span>
        </Button>
      ),
    },
  ];
  return (
    <AdminPage title="Technicians" description="Skills, weekly availability and time off. To change a technician's role or activation use Staff.">
      <Panel bodyClassName="p-0">
        <DataTable caption="Technicians" columns={columns} rows={q.data?.items} rowKey={(t) => t.membership_id} loading={q.isLoading} error={q.error} onRetry={() => q.refetch()} page={page} pageSize={20} total={q.data?.total ?? 0} onPageChange={setPage} />
      </Panel>
      {open && <TechnicianDialog key={open} id={open} onClose={() => setOpen(null)} />}
    </AdminPage>
  );
}
