"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Pencil } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Button, Dialog, FormField, FormServerError, Input, Textarea } from "@/components/ui";
import type { RequestDetail } from "@/lib/api/types";
import { useApiMutation } from "@/lib/query/hooks";
import { qk } from "@/lib/query/keys";
import type { RequestActionContext, RequestActionProps } from "@/features/request-actions/types";
import { utcIsoToZoned, zonedToUtcIso } from "./org-time";
import { editRequestSchema } from "./schema";
import type { EditRequestValues } from "./schema";
import { mapServerErrors } from "./server-errors";
import { WindowFields } from "./window-fields";

function defaultsFor(d: RequestDetail, tz: string): EditRequestValues {
  const s = d.preferred_window_start ? utcIsoToZoned(d.preferred_window_start, tz) : null;
  const e = d.preferred_window_end ? utcIsoToZoned(d.preferred_window_end, tz) : null;
  return { title: d.title, description: d.description, window_date: s?.date ?? "", window_start: s?.time ?? "", window_end: e?.time ?? "" };
}

function EditForm({ ctx, onDone }: { ctx: RequestActionContext; onDone: () => void }) {
  const form = useForm<EditRequestValues>({ resolver: zodResolver(editRequestSchema), defaultValues: defaultsFor(ctx.detail, ctx.timezone) });
  const m = useApiMutation<RequestDetail, Record<string, unknown>>({
    request: (body) => ({ method: "PATCH", path: `/requests/${ctx.requestId}`, body }),
    invalidate: (orgId) => [qk.requests.detail(orgId, ctx.requestId), qk.requests.all(orgId)],
    successMessage: "Request updated.",
    errorMessage: false,
    onError: (e) => mapServerErrors(form, e),
  });
  const { errors } = form.formState;

  const submit = form.handleSubmit((v) => {
    const hasWindow = Boolean(v.window_date && v.window_start && v.window_end);
    m.mutate(
      {
        title: v.title.trim(),
        description: v.description.trim(),
        preferred_window_start: hasWindow ? zonedToUtcIso(v.window_date!, v.window_start!, ctx.timezone) : null,
        preferred_window_end: hasWindow ? zonedToUtcIso(v.window_date!, v.window_end!, ctx.timezone) : null,
      },
      { onSuccess: onDone },
    );
  });

  return (
    <form onSubmit={submit} noValidate className="flex flex-col gap-4" aria-label="Edit request">
      <FormServerError form={form} />
      <FormField label="Title" required error={errors.title?.message}>
        <Input {...form.register("title")} />
      </FormField>
      <FormField label="Description" required error={errors.description?.message}>
        <Textarea rows={6} {...form.register("description")} />
      </FormField>
      <WindowFields register={form.register as never} errors={errors} timezone={ctx.timezone} />
      <div className="flex flex-wrap justify-end gap-2">
        <Button variant="secondary" disabled={m.isPending} onClick={onDone}>
          Discard changes
        </Button>
        <Button type="submit" loading={m.isPending}>
          Save changes
        </Button>
      </div>
    </form>
  );
}

/** Edit title / description / preferred window while the request is still SUBMITTED. */
export function EditRequestAction({ ctx }: RequestActionProps) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button variant="secondary" onClick={() => setOpen(true)}>
        <Pencil className="size-4" aria-hidden /> Edit request
      </Button>
      <Dialog open={open} onOpenChange={setOpen} title="Edit request" description="You can change these details until the request is triaged.">
        {/* Mounted only while open so the form always starts from the latest server values. */}
        {open && <EditForm ctx={ctx} onDone={() => setOpen(false)} />}
      </Dialog>
    </>
  );
}
