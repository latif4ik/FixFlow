"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMemo } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { Button, ErrorState, FormField, FormServerError, InlineNote, Input, Panel, Select, Skeleton } from "@/components/ui";
import type { Schemas } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { qk, useApiMutation, useApiQuery } from "@/lib/query";
import { AdminPage, SectionHint } from "./shared";

type Org = Schemas["OrgOut"];

const schema = z.object({
  name: z.string().trim().min(2, "Enter at least 2 characters.").max(120, "At most 120 characters."),
  timezone: z.string().min(1, "Choose a time zone."),
});
type FormValues = z.infer<typeof schema>;

function timezones(current?: string): string[] {
  const list = typeof Intl.supportedValuesOf === "function" ? Intl.supportedValuesOf("timeZone") : [];
  const set = new Set(list);
  if (current) set.add(current);
  set.add("UTC");
  return [...set].sort();
}

function OrgForm({ org }: { org: Org }) {
  const zones = useMemo(() => timezones(org.timezone), [org.timezone]);
  const form = useForm<FormValues>({ resolver: zodResolver(schema), defaultValues: { name: org.name, timezone: org.timezone } });
  const { setOrgTimezone } = useAuth();
  const save = useApiMutation<Org, FormValues>({
    request: (v) => ({ method: "PATCH", path: "/org", body: v }),
    invalidate: (o) => [qk.org.settings(o)],
    successMessage: "Organization settings saved.",
    onSuccess: (saved) => setOrgTimezone(saved.timezone),
    form,
  });
  return (
    <form onSubmit={form.handleSubmit((v) => save.mutate(v))} noValidate className="flex max-w-xl flex-col gap-4">
      <FormField label="Organization name" error={form.formState.errors.name?.message} required>
        <Input {...form.register("name")} autoComplete="organization" />
      </FormField>
      <FormField label="Time zone" error={form.formState.errors.timezone?.message} hint="Dates, business hours and the dashboard day use this zone." required>
        <Select {...form.register("timezone")}>
          {zones.map((z) => (
            <option key={z} value={z}>
              {z}
            </option>
          ))}
        </Select>
      </FormField>
      <FormServerError form={form} />
      <div>
        <Button type="submit" loading={save.isPending}>
          Save settings
        </Button>
      </div>
      <p className="text-[13px] text-muted">URL slug: {org.slug}</p>
    </form>
  );
}

function Escalation() {
  const run = useApiMutation<Schemas["EscalationResult"], void>({
    request: () => ({ path: "/admin/sla/escalate" }),
    idempotent: true,
    invalidate: (o) => [qk.dashboard.all(o), qk.requests.all(o), qk.notifications.all(o)],
  });
  return (
    <Panel title="SLA escalation">
      <SectionHint>Escalation normally runs on a schedule. Run it now to flag overdue requests and notify dispatchers immediately.</SectionHint>
      <div className="mt-3 flex flex-wrap items-center gap-3">
        <Button variant="secondary" loading={run.isPending} onClick={() => run.mutate()}>
          Run escalation check now
        </Button>
        {run.data && (
          <div role="status">
            <InlineNote tone="success">
              {run.data.escalated === 0 ? "Nothing to escalate: no newly overdue requests." : `${run.data.escalated} ${run.data.escalated === 1 ? "request was" : "requests were"} escalated.`}
            </InlineNote>
          </div>
        )}
      </div>
    </Panel>
  );
}

export function OrganizationPage() {
  const q = useApiQuery<Org>({ queryKey: (o) => qk.org.settings(o), path: "/org" });
  return (
    <AdminPage title="Organization" description="Name and time zone of this organization.">
      <Panel title="Settings">
        {q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : !q.data ? <Skeleton className="h-40 w-full max-w-xl" /> : <OrgForm key={`${q.data.name}|${q.data.timezone}`} org={q.data} />}
      </Panel>
      <Escalation />
    </AdminPage>
  );
}
