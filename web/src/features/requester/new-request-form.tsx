"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { Flag } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { Button, EmptyState, ErrorState, FormField, FormServerError, Input, LoadingState, Panel, PageHeader, Select, Textarea, buttonStyles, toast } from "@/components/ui";
import { api, apiFetch, isApiError, newIdempotencyKey } from "@/lib/api/client";
import type { Page, Schemas } from "@/lib/api/types";
import { useAuth } from "@/lib/auth/auth-context";
import { cn } from "@/lib/cn";
import { useApiQuery } from "@/lib/query/hooks";
import { qk } from "@/lib/query/keys";
import { ImagePicker } from "./image-picker";
import type { PickedImage } from "./image-picker";
import { zonedToUtcIso } from "./org-time";
import { DESC_MAX, MAX_IMAGES, TITLE_MAX, newRequestSchema, validateImage } from "./schema";
import type { NewRequestValues } from "./schema";
import { mapServerErrors } from "./server-errors";
import { WindowFields } from "./window-fields";

type Property = Schemas["PropertyOut"];
type Asset = Schemas["AssetOut"];
type Category = Schemas["CategoryOut"];

const PRIORITY_OPTIONS = [
  { value: "LOW", label: "Low", hint: "Can wait" },
  { value: "NORMAL", label: "Normal", hint: "Standard" },
  { value: "HIGH", label: "High", hint: "Urgent" },
] as const;

export function NewRequestForm() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { orgId, timezone } = useAuth();

  const props = useApiQuery<Page<Property>>({ queryKey: (o) => qk.properties.list(o, { requester: true }), path: "/properties", query: { page_size: 100 } });
  const cats = useApiQuery<Page<Category>>({ queryKey: (o) => qk.categories.list(o, { enabled: true }), path: "/categories", query: { page_size: 100 } });

  const form = useForm<NewRequestValues>({
    resolver: zodResolver(newRequestSchema),
    defaultValues: { title: "", description: "", category_id: "", property_id: "", asset_id: "", priority: "NORMAL", window_date: "", window_start: "", window_end: "" },
  });
  const { register, handleSubmit, setValue, formState, control } = form;
  const { errors } = formState;
  const propertyId = useWatch({ control, name: "property_id" });
  const description = useWatch({ control, name: "description" });

  const assets = useApiQuery<Page<Asset>>({
    queryKey: (o) => qk.assets.list(o, { property_id: propertyId, picker: true }),
    path: "/assets",
    query: { property_id: propertyId, page_size: 100 },
    enabled: Boolean(propertyId),
  });

  const [images, setImages] = useState<PickedImage[]>([]);
  const [imageError, setImageError] = useState<string | null>(null);
  const [created, setCreated] = useState<{ id: string; display_id: string } | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const busy = useRef(false);
  const idemKey = useRef<string | null>(null);

  function addImages(files: File[]) {
    const problems: string[] = [];
    const next = [...images];
    for (const f of files) {
      if (next.length >= MAX_IMAGES) {
        problems.push(`You can attach at most ${MAX_IMAGES} photos.`);
        break;
      }
      const bad = validateImage(f);
      if (bad) problems.push(bad);
      else next.push({ id: crypto.randomUUID(), file: f, state: "idle" });
    }
    setImages(next);
    setImageError(problems.length ? problems.join(" ") : null);
  }

  function patchImage(id: string, patch: Partial<PickedImage>) {
    setImages((cur) => cur.map((i) => (i.id === id ? { ...i, ...patch } : i)));
  }

  async function uploadOne(requestId: string, im: PickedImage, index: number): Promise<boolean> {
    patchImage(im.id, { state: "uploading", error: undefined });
    const fd = new FormData();
    fd.append("file", im.file);
    fd.append("purpose", "INTAKE");
    fd.append("client_command_id", im.id);
    fd.append("client_index", String(index));
    try {
      await api.upload(`/requests/${requestId}/files`, fd, { orgId });
      patchImage(im.id, { state: "done" });
      return true;
    } catch (e) {
      patchImage(im.id, { state: "failed", error: isApiError(e) ? e.message : "Upload failed." });
      return false;
    }
  }

  async function retryOne(id: string) {
    if (!created || busy.current) return;
    const index = images.findIndex((i) => i.id === id);
    const im = images[index];
    if (!im) return;
    busy.current = true;
    setSubmitting(true);
    const ok = await uploadOne(created.id, im, index);
    busy.current = false;
    setSubmitting(false);
    // Navigate once nothing is left to retry.
    if (ok && images.every((i) => i.id === id || i.state === "done")) router.push(`/requests/${created.id}`);
  }

  async function onSubmit(v: NewRequestValues) {
    if (busy.current || created) return;
    busy.current = true;
    setSubmitting(true);
    try {
      let start: string | null = null;
      let end: string | null = null;
      if (v.window_date && v.window_start && v.window_end) {
        start = zonedToUtcIso(v.window_date, v.window_start, timezone);
        end = zonedToUtcIso(v.window_date, v.window_end, timezone);
      }
      const body = {
        title: v.title.trim(),
        description: v.description.trim(),
        category_id: v.category_id,
        property_id: v.property_id,
        asset_id: v.asset_id || null,
        priority: v.priority,
        preferred_window_start: start,
        preferred_window_end: end,
      };
      idemKey.current ??= newIdempotencyKey();
      let req: { id: string; display_id: string };
      try {
        req = await apiFetch<{ id: string; display_id: string }>("/requests", { method: "POST", body, idempotencyKey: idemKey.current, orgId });
      } catch (e) {
        // A definitive server answer (4xx) means a retry is a new attempt; network/5xx errors keep the key so a retry is idempotent.
        if (isApiError(e) && e.status >= 400 && e.status < 500) idemKey.current = null;
        if (isApiError(e) && e.status === 401) return;
        mapServerErrors(form, e);
        if (isApiError(e) && e.status !== 422) toast.error(e.message);
        return;
      }
      setCreated(req);
      if (orgId) void queryClient.invalidateQueries({ queryKey: qk.requests.all(orgId) });
      let failed = 0;
      for (let i = 0; i < images.length; i++) {
        const ok = await uploadOne(req.id, images[i]!, i);
        if (!ok) failed++;
      }
      if (failed === 0) {
        toast.success(`${req.display_id} submitted.`);
        router.push(`/requests/${req.id}`);
      } else {
        toast.warning(`${req.display_id} was created, but ${failed} photo${failed > 1 ? "s" : ""} could not be uploaded.`);
      }
    } finally {
      busy.current = false;
      setSubmitting(false);
    }
  }

  if (props.isLoading || cats.isLoading) return <LoadingState label="Loading form" />;
  if (props.error) return <ErrorState error={props.error} onRetry={() => void props.refetch()} />;
  if (cats.error) return <ErrorState error={cats.error} onRetry={() => void cats.refetch()} />;

  const properties = (props.data?.items ?? []).filter((p) => p.is_active);
  const categories = (cats.data?.items ?? []).filter((c) => c.is_enabled);

  if (properties.length === 0) {
    return (
      <>
        <PageHeader title="New request" breadcrumb={[{ label: "My requests", href: "/requests" }, { label: "New request" }]} />
        <Panel>
          <EmptyState
            title="No properties available to you"
            description="You can only submit requests for properties you have been granted access to. Ask your organization's administrator to give you access."
            action={
              <Link href="/requests" className={buttonStyles({ variant: "secondary" })}>
                Back to my requests
              </Link>
            }
          />
        </Panel>
      </>
    );
  }

  const assetOptions = (assets.data?.items ?? []).filter((a) => a.status !== "RETIRED");
  const locked = submitting || created !== null;

  return (
    <>
      <PageHeader
        title="New request"
        description="Describe the problem and we will route it to the right team."
        breadcrumb={[{ label: "My requests", href: "/requests" }, { label: "New request" }]}
      />
      <form onSubmit={(e) => void handleSubmit(onSubmit)(e)} noValidate aria-label="New request" className="max-w-3xl">
        <Panel>
          <div className="flex flex-col gap-5">
            <FormServerError form={form} />
            <FormField label="Title" required error={errors.title?.message} hint={`Short summary, up to ${TITLE_MAX} characters.`}>
              <Input maxLength={TITLE_MAX + 20} disabled={locked} {...register("title")} />
            </FormField>
            <FormField label="Description" required error={errors.description?.message} hint={`What is wrong, where exactly, and since when. ${description?.length ?? 0} / ${DESC_MAX}`}>
              <Textarea rows={6} disabled={locked} {...register("description")} />
            </FormField>
            <div className="grid gap-4 sm:grid-cols-2">
              <FormField label="Category" required error={errors.category_id?.message}>
                <Select disabled={locked} {...register("category_id")}>
                  <option value="">Select a category</option>
                  {categories.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </Select>
              </FormField>
              <FormField label="Property" required error={errors.property_id?.message}>
                <Select
                  disabled={locked}
                  {...register("property_id", {
                    onChange: () => setValue("asset_id", ""),
                  })}
                >
                  <option value="">Select a property</option>
                  {properties.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
                </Select>
              </FormField>
            </div>
            <FormField
              label="Asset (optional)"
              error={errors.asset_id?.message}
              hint={!propertyId ? "Choose a property first to pick an asset." : assets.isLoading ? "Loading assets..." : assetOptions.length === 0 ? "No assets registered for this property." : undefined}
            >
              <Select disabled={locked || !propertyId || assets.isLoading} {...register("asset_id")}>
                <option value="">No specific asset</option>
                {assetOptions.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.code} - {a.name}
                  </option>
                ))}
              </Select>
            </FormField>

            <fieldset className="flex flex-col gap-2" disabled={locked}>
              <legend className="text-[13px] font-semibold text-ink">Priority</legend>
              <div role="radiogroup" aria-label="Priority" className="inline-flex w-full max-w-md overflow-hidden rounded-md border border-border-strong sm:w-auto">
                {PRIORITY_OPTIONS.map((o) => (
                  <label
                    key={o.value}
                    className={cn(
                      "flex flex-1 cursor-pointer flex-col items-center gap-0.5 border-r border-border-strong px-4 py-2 text-sm font-semibold last:border-r-0 sm:flex-none",
                      "has-[:checked]:bg-primary-tint has-[:checked]:text-primary-dark has-[:focus-visible]:outline has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-primary",
                    )}
                  >
                    <input type="radio" value={o.value} className="sr-only" {...register("priority")} />
                    <span className="inline-flex items-center gap-1.5">
                      <Flag className="size-3.5" aria-hidden /> {o.label}
                    </span>
                    <span className="text-[12px] font-normal text-muted">{o.hint}</span>
                  </label>
                ))}
              </div>
            </fieldset>

            <WindowFields register={register as never} errors={errors} timezone={timezone} />

            <ImagePicker
              images={images}
              onAdd={addImages}
              onRemove={(id) => setImages((cur) => cur.filter((i) => i.id !== id))}
              onRetry={(id) => void retryOne(id)}
              disabled={submitting && created === null}
              error={imageError}
            />

            {created && images.some((i) => i.state === "failed") && (
              <div role="alert" className="flex flex-wrap items-center justify-between gap-3 rounded-md bg-warning-tint px-3 py-2 text-sm text-warning-dark">
                <span>
                  {created.display_id} was created. Some photos did not upload: retry them here, or continue and add them later.
                </span>
                <Link href={`/requests/${created.id}`} className={buttonStyles({ variant: "secondary", size: "sm" })}>
                  Open {created.display_id}
                </Link>
              </div>
            )}

            <div className="flex flex-wrap justify-end gap-2">
              <Link href="/requests" className={buttonStyles({ variant: "secondary" })} aria-disabled={locked || undefined}>
                Cancel
              </Link>
              <Button type="submit" loading={submitting} disabled={created !== null}>
                {submitting ? (created ? "Uploading photos" : "Submitting") : "Submit request"}
              </Button>
            </div>
          </div>
        </Panel>
      </form>
    </>
  );
}
