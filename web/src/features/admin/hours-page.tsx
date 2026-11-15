"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Trash2 } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { Button, ConfirmDialog, EmptyState, ErrorState, FormField, FormServerError, IconButton, Input, Panel, Skeleton } from "@/components/ui";
import type { Page, Schemas } from "@/lib/api";
import { DateTime } from "@/components/ui";
import { qk, useApiMutation, useApiQuery } from "@/lib/query";
import { AdminPage, hhmm, SectionHint, withSeconds } from "./shared";
import { WeekEditor } from "./week-editor";
import type { DayInterval } from "./week-editor";

type Hours = Schemas["BusinessHoursBody"];
type Holiday = Schemas["HolidayOut"];

function BusinessHours() {
  const q = useApiQuery<Hours>({ queryKey: (o) => qk.org.businessHours(o), path: "/org/business-hours" });
  const save = useApiMutation<Hours, DayInterval[]>({
    request: (v) => ({ method: "PUT", path: "/org/business-hours", body: { intervals: v.map((i) => ({ weekday: i.weekday, open_time: withSeconds(i.start), close_time: withSeconds(i.end) })) } }),
    invalidate: (o) => [qk.org.businessHours(o)],
    successMessage: "Business hours saved.",
  });
  return (
    <Panel title="Weekly business hours">
      <SectionHint>Add several intervals on a day for a lunch break. A day without intervals is closed. Times are in the organization time zone.</SectionHint>
      <div className="mt-3">
        {q.error ? (
          <ErrorState error={q.error} onRetry={() => q.refetch()} />
        ) : !q.data ? (
          <Skeleton className="h-64 w-full" />
        ) : (
          <WeekEditor
            key={JSON.stringify(q.data.intervals)}
            idPrefix="Business hours"
            initial={q.data.intervals.map((i) => ({ weekday: i.weekday, start: hhmm(i.open_time), end: hhmm(i.close_time) }))}
            saving={save.isPending}
            saveLabel="Save business hours"
            onSave={(v) => save.mutateAsync(v).catch(() => undefined)}
          />
        )}
      </div>
    </Panel>
  );
}

const holidaySchema = z.object({
  date: z.string().min(1, "Choose a date."),
  name: z.string().trim().min(1, "Enter a name.").max(120, "At most 120 characters."),
});
type HolidayForm = z.infer<typeof holidaySchema>;

function Holidays() {
  const q = useApiQuery<Page<Holiday>>({ queryKey: (o) => qk.org.holidays(o), path: "/org/holidays", query: { page_size: 100 } });
  const form = useForm<HolidayForm>({ resolver: zodResolver(holidaySchema), defaultValues: { date: "", name: "" } });
  const add = useApiMutation<Holiday, HolidayForm>({
    request: (v) => ({ path: "/org/holidays", body: v }),
    idempotent: true,
    invalidate: (o) => [qk.org.holidays(o)],
    successMessage: "Holiday added.",
    form,
    onSuccess: () => form.reset({ date: "", name: "" }),
  });
  const del = useApiMutation<unknown, string>({
    request: (id) => ({ method: "DELETE", path: `/org/holidays/${id}` }),
    invalidate: (o) => [qk.org.holidays(o)],
    successMessage: "Holiday deleted.",
  });
  const [toDelete, setToDelete] = useState<Holiday | null>(null);

  return (
    <Panel title="Holidays">
      <form onSubmit={form.handleSubmit((v) => add.mutate(v))} noValidate aria-label="Add holiday" className="flex flex-wrap items-start gap-3">
        <FormField label="Date" error={form.formState.errors.date?.message} required>
          <Input type="date" {...form.register("date")} className="w-44" />
        </FormField>
        <FormField label="Name" error={form.formState.errors.name?.message} required>
          <Input {...form.register("name")} className="w-64" />
        </FormField>
        <div className="pt-[26px]">
          <Button type="submit" loading={add.isPending}>
            Add holiday
          </Button>
        </div>
        <div className="w-full">
          <FormServerError form={form} />
        </div>
      </form>
      <div className="mt-4">
        {q.error ? (
          <ErrorState error={q.error} onRetry={() => q.refetch()} />
        ) : !q.data ? (
          <Skeleton className="h-20 w-full" />
        ) : q.data.items.length === 0 ? (
          <EmptyState title="No holidays" description="Days listed here count as closed for scheduling." />
        ) : (
          <ul className="divide-y divide-border">
            {q.data.items.map((h) => (
              <li key={h.id} className="flex items-center justify-between gap-3 py-2.5 text-sm">
                <span>
                  <strong className="text-ink">{h.name}</strong> <span className="text-muted">·</span> <DateTime value={`${h.date}T12:00:00Z`} style="date" tz="UTC" />
                </span>
                <IconButton aria-label={`Delete holiday ${h.name}`} variant="ghost" icon={<Trash2 className="size-4" aria-hidden />} onClick={() => setToDelete(h)} />
              </li>
            ))}
          </ul>
        )}
      </div>
      <ConfirmDialog
        open={toDelete !== null}
        onOpenChange={(o) => !o && setToDelete(null)}
        title="Delete this holiday?"
        description={toDelete ? `${toDelete.name} (${toDelete.date}) will count as a working day again.` : undefined}
        confirmLabel="Delete holiday"
        onConfirm={() => del.mutateAsync(toDelete!.id)}
      />
    </Panel>
  );
}

export function HoursPage() {
  return (
    <AdminPage title="Business hours and holidays" description="Working time used for SLA due dates and scheduling.">
      <BusinessHours />
      <Holidays />
    </AdminPage>
  );
}
