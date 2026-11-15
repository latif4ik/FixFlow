"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Star } from "lucide-react";
import { useForm, useWatch } from "react-hook-form";
import { z } from "zod";
import { Button, FormField, FormServerError, Panel, Textarea } from "@/components/ui";
import { cn } from "@/lib/cn";
import { useApiMutation } from "@/lib/query/hooks";
import { qk } from "@/lib/query/keys";
import type { RequestActionProps } from "@/features/request-actions/types";
import { mapServerErrors } from "./server-errors";

const RATING_LABELS = ["Poor", "Fair", "Good", "Very good", "Excellent"];

const schema = z.object({
  rating: z.string().regex(/^[1-5]$/, "Choose a rating from 1 to 5."),
  comment: z.string().trim().max(1000, "Comment must be at most 1000 characters.").optional(),
});
type Values = z.infer<typeof schema>;

/** Satisfaction feedback after the work is completed (shown until feedback exists). */
export function FeedbackFormPanel({ ctx }: RequestActionProps) {
  const form = useForm<Values>({ resolver: zodResolver(schema), defaultValues: { rating: "", comment: "" } });
  const rating = Number(useWatch({ control: form.control, name: "rating" })) || 0;
  const m = useApiMutation<unknown, { rating: number; comment: string | null }>({
    request: (body) => ({ path: `/requests/${ctx.requestId}/feedback`, body }),
    idempotent: true,
    invalidate: (orgId) => [qk.requests.detail(orgId, ctx.requestId), qk.requests.all(orgId)],
    successMessage: "Thanks for your feedback!",
    errorMessage: false,
    onError: (e) => mapServerErrors(form, e),
  });

  const submit = form.handleSubmit((v) => m.mutate({ rating: Number(v.rating), comment: v.comment?.trim() ? v.comment.trim() : null }));

  return (
    <Panel title="How did we do?">
      <form onSubmit={submit} noValidate aria-label="Satisfaction feedback" className="flex flex-col gap-4">
        <FormServerError form={form} />
        <fieldset className="flex flex-col gap-2" aria-describedby={form.formState.errors.rating ? "rating-error" : undefined}>
          <legend className="text-[13px] font-semibold text-ink">Rate the service (1 = poor, 5 = excellent)</legend>
          <div className="flex flex-wrap gap-2">
            {RATING_LABELS.map((label, i) => {
              const n = i + 1;
              return (
                <label
                  key={n}
                  className={cn(
                    "flex min-w-20 cursor-pointer flex-col items-center gap-0.5 rounded-md border px-3 py-2 text-sm font-semibold",
                    rating === n ? "border-primary bg-primary-tint text-primary-dark" : "border-border-strong text-text hover:bg-canvas",
                    "has-[:focus-visible]:outline has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-primary",
                  )}
                >
                  <input type="radio" value={String(n)} className="sr-only" aria-label={`${n} out of 5, ${label}`} {...form.register("rating")} />
                  <span className="inline-flex items-center gap-1">
                    <Star className={cn("size-4", rating >= n && "fill-warning text-warning")} aria-hidden /> {n}
                  </span>
                  <span className="text-[12px] font-normal text-muted">{label}</span>
                </label>
              );
            })}
          </div>
          {form.formState.errors.rating && (
            <p id="rating-error" role="alert" className="text-[13px] font-medium text-danger-dark">
              {form.formState.errors.rating.message}
            </p>
          )}
        </fieldset>
        <FormField label="Comment (optional)" error={form.formState.errors.comment?.message}>
          <Textarea rows={3} maxLength={1100} {...form.register("comment")} />
        </FormField>
        <div>
          <Button type="submit" loading={m.isPending}>
            Send feedback
          </Button>
        </div>
      </form>
    </Panel>
  );
}
