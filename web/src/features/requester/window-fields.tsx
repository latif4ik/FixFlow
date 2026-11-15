"use client";

import type { FieldErrors, UseFormRegister } from "react-hook-form";
import { FormField, Input } from "@/components/ui";

interface WindowValues {
  window_date?: string;
  window_start?: string;
  window_end?: string;
}

/** Optional preferred visit window: date + start/end time, interpreted in the ORGANIZATION timezone. */
export function WindowFields({
  register,
  errors,
  timezone,
}: {
  register: UseFormRegister<WindowValues & Record<string, unknown>>;
  errors: FieldErrors<WindowValues>;
  timezone: string;
}) {
  return (
    <fieldset className="flex flex-col gap-2">
      <legend className="text-[13px] font-semibold text-ink">Preferred visit time (optional)</legend>
      <p className="text-[13px] text-muted">Times are in your organization&apos;s timezone ({timezone}).</p>
      <div className="grid gap-3 sm:grid-cols-3">
        <FormField label="Date" error={errors.window_date?.message}>
          <Input type="date" {...register("window_date")} />
        </FormField>
        <FormField label="From" error={errors.window_start?.message}>
          <Input type="time" {...register("window_start")} />
        </FormField>
        <FormField label="To" error={errors.window_end?.message}>
          <Input type="time" {...register("window_end")} />
        </FormField>
      </div>
    </fieldset>
  );
}
