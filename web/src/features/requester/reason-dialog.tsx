"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { Button, Dialog, FormField, FormServerError, Textarea } from "@/components/ui";
import { isApiError } from "@/lib/api/client";

/**
 * Dialog that asks for a reason (required with `minLength`, otherwise optional) before a consequential action.
 * `onSubmit` should reject on failure so the dialog stays open; the 422/409 message is shown inline.
 */
export function ReasonDialog({
  open,
  onOpenChange,
  title,
  description,
  label = "Reason",
  minLength = 0,
  confirmLabel,
  cancelLabel = "Keep as is",
  destructive,
  onSubmit,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  title: string;
  description?: string;
  label?: string;
  /** 0 = optional. */
  minLength?: number;
  confirmLabel: string;
  cancelLabel?: string;
  destructive?: boolean;
  onSubmit: (reason: string) => Promise<unknown>;
}) {
  const schema = z.object({
    reason: z
      .string()
      .trim()
      .max(500, "Reason must be at most 500 characters.")
      .refine((v) => minLength === 0 || v.length >= minLength, `Please give a reason of at least ${minLength} characters.`),
  });
  const form = useForm<{ reason: string }>({ resolver: zodResolver(schema), defaultValues: { reason: "" } });
  const { handleSubmit, register, reset, setError, formState } = form;

  useEffect(() => {
    if (!open) reset({ reason: "" });
  }, [open, reset]);

  const submit = handleSubmit(async (v) => {
    try {
      await onSubmit(v.reason.trim());
      onOpenChange(false);
    } catch (e) {
      if (isApiError(e) && e.status === 422) {
        const fe = e.fieldErrors.find((f) => f.field.endsWith("reason"));
        setError(fe ? "reason" : "root.server", { type: "server", message: fe?.message ?? e.message });
      } else if (isApiError(e) && e.status === 401) {
        /* session-expired screen handles it */
      } else {
        setError("root.server", { type: "server", message: isApiError(e) ? e.message : "Something went wrong. Try again." });
      }
    }
  });

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        if (!formState.isSubmitting) onOpenChange(o);
      }}
      title={title}
      description={description}
    >
      <form onSubmit={submit} noValidate className="flex flex-col gap-4">
        <FormServerError form={form} />
        <FormField label={label} required={minLength > 0} error={formState.errors.reason?.message} hint={minLength > 0 ? `At least ${minLength} characters.` : "Optional."}>
          <Textarea rows={4} maxLength={600} {...register("reason")} />
        </FormField>
        <div className="flex flex-wrap justify-end gap-2">
          <Button variant="secondary" disabled={formState.isSubmitting} onClick={() => onOpenChange(false)}>
            {cancelLabel}
          </Button>
          <Button type="submit" variant={destructive ? "danger" : "primary"} loading={formState.isSubmitting}>
            {confirmLabel}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
