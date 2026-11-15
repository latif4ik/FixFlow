"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Pencil, Plus } from "lucide-react";
import { useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { z } from "zod";
import { Badge, Button, Checkbox, DataTable, Dialog, EmptyState, ErrorState, FormField, FormServerError, IconButton, Input, Label, Panel, Skeleton, Switch, Textarea } from "@/components/ui";
import type { Column } from "@/components/ui";
import type { Page, Schemas } from "@/lib/api";
import { qk, useApiMutation, useApiQuery } from "@/lib/query";
import { AdminPage, SectionHint } from "./shared";

type Skill = Schemas["SkillOut"];
type Category = Schemas["CategoryOut"];

/* ---------------- skills ---------------- */

const skillSchema = z.object({ name: z.string().trim().min(2, "Enter at least 2 characters.").max(60, "At most 60 characters.") });
type SkillForm = z.infer<typeof skillSchema>;

function SkillDialog({ skill, open, onOpenChange }: { skill: Skill | null; open: boolean; onOpenChange: (o: boolean) => void }) {
  const form = useForm<SkillForm>({ resolver: zodResolver(skillSchema), values: { name: skill?.name ?? "" } });
  const save = useApiMutation<Skill, SkillForm>({
    request: (v) => (skill ? { method: "PATCH", path: `/skills/${skill.id}`, body: v } : { path: "/skills", body: v }),
    idempotent: !skill,
    invalidate: (o) => [qk.skills.all(o), qk.categories.all(o), qk.technicians.all(o)],
    successMessage: skill ? "Skill renamed." : "Skill added.",
    form,
    onSuccess: () => onOpenChange(false),
  });
  return (
    <Dialog open={open} onOpenChange={onOpenChange} title={skill ? "Rename skill" : "Add a skill"}>
      <form onSubmit={form.handleSubmit((v) => save.mutate(v))} noValidate className="flex flex-col gap-4">
        <FormField label="Skill name" error={form.formState.errors.name?.message} required>
          <Input {...form.register("name")} />
        </FormField>
        <FormServerError form={form} />
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button type="submit" loading={save.isPending}>
            {skill ? "Save" : "Add skill"}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}

function Skills() {
  const q = useApiQuery<Page<Skill>>({ queryKey: (o) => qk.skills.list(o, { all: true }), path: "/skills", query: { page_size: 100 } });
  const [dialog, setDialog] = useState<{ skill: Skill | null } | null>(null);
  return (
    <Panel
      title="Skills"
      actions={
        <Button size="sm" onClick={() => setDialog({ skill: null })}>
          <Plus className="size-4" aria-hidden /> Add skill
        </Button>
      }
    >
      <SectionHint>Skills are required by categories and held by technicians; smart assignment uses them.</SectionHint>
      <div className="mt-3">
        {q.error ? (
          <ErrorState error={q.error} onRetry={() => q.refetch()} />
        ) : !q.data ? (
          <Skeleton className="h-16 w-full" />
        ) : q.data.items.length === 0 ? (
          <EmptyState title="No skills yet" />
        ) : (
          <ul className="flex flex-wrap gap-2">
            {q.data.items.map((s) => (
              <li key={s.id} className="flex items-center gap-1 rounded-pill bg-canvas-2 py-1 pl-3 pr-1 text-sm font-semibold text-text">
                {s.name}
                <IconButton aria-label={`Rename skill ${s.name}`} size="sm" variant="ghost" className="size-7 !px-0" icon={<Pencil className="size-3.5" aria-hidden />} onClick={() => setDialog({ skill: s })} />
              </li>
            ))}
          </ul>
        )}
      </div>
      {dialog && <SkillDialog key={dialog.skill?.id ?? "new"} skill={dialog.skill} open onOpenChange={(o) => !o && setDialog(null)} />}
    </Panel>
  );
}

/* ---------------- categories ---------------- */

const catSchema = z.object({
  name: z.string().trim().min(2, "Enter at least 2 characters.").max(80, "At most 80 characters."),
  description: z.string().max(500, "At most 500 characters."),
  default_duration_minutes: z.number({ error: "Enter the duration in minutes." }).int("Use whole minutes.").min(30, "At least 30 minutes.").max(1440, "At most 1440 minutes."),
  required_skill_ids: z.array(z.string()),
  is_enabled: z.boolean(),
});
type CatForm = z.infer<typeof catSchema>;

function CategoryDialog({ category, skills, onClose }: { category: Category | null; skills: Skill[]; onClose: () => void }) {
  const form = useForm<CatForm>({
    resolver: zodResolver(catSchema),
    defaultValues: {
      name: category?.name ?? "",
      description: category?.description ?? "",
      default_duration_minutes: category?.default_duration_minutes ?? 60,
      required_skill_ids: category?.required_skills.map((s) => s.id) ?? [],
      is_enabled: category?.is_enabled ?? true,
    },
  });
  const save = useApiMutation<Category, CatForm>({
    request: (v) => {
      const body = { ...v, description: v.description.trim() || null };
      return category ? { method: "PATCH", path: `/categories/${category.id}`, body } : { path: "/categories", body };
    },
    idempotent: !category,
    invalidate: (o) => [qk.categories.all(o)],
    successMessage: category ? "Category saved." : "Category created.",
    form,
    onSuccess: onClose,
  });
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()} title={category ? `Edit ${category.name}` : "New category"} className="max-w-xl">
      <form onSubmit={form.handleSubmit((v) => save.mutate(v))} noValidate className="flex flex-col gap-4">
        <FormField label="Name" error={form.formState.errors.name?.message} required>
          <Input {...form.register("name")} />
        </FormField>
        <FormField label="Description" error={form.formState.errors.description?.message}>
          <Textarea rows={3} {...form.register("description")} />
        </FormField>
        <FormField label="Default duration (minutes)" hint="Used to size appointments. At least 30." error={form.formState.errors.default_duration_minutes?.message} required>
          <Input type="number" min={30} step={5} {...form.register("default_duration_minutes", { valueAsNumber: true })} />
        </FormField>
        <fieldset className="flex flex-col gap-2">
          <legend className="mb-1 text-[13px] font-semibold text-ink">Required skills</legend>
          {skills.length === 0 && <p className="text-sm text-muted">No skills defined yet. Add skills first.</p>}
          <Controller
            control={form.control}
            name="required_skill_ids"
            render={({ field }) => (
              <div className="grid grid-cols-2 gap-2">
                {skills.map((s) => {
                  const checked = field.value.includes(s.id);
                  return (
                    <div key={s.id} className="flex items-center gap-2">
                      <Checkbox id={`req-skill-${s.id}`} checked={checked} onCheckedChange={(c) => field.onChange(c === true ? [...field.value, s.id] : field.value.filter((x) => x !== s.id))} />
                      <Label htmlFor={`req-skill-${s.id}`} className="font-normal">
                        {s.name}
                      </Label>
                    </div>
                  );
                })}
              </div>
            )}
          />
        </fieldset>
        <Controller
          control={form.control}
          name="is_enabled"
          render={({ field }) => (
            <div className="flex items-center gap-3">
              <Switch id="cat-enabled" checked={field.value} onCheckedChange={field.onChange} />
              <Label htmlFor="cat-enabled">Enabled (requesters can choose this category)</Label>
            </div>
          )}
        />
        <FormServerError form={form} />
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={save.isPending}>
            {category ? "Save category" : "Create category"}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}

function Categories() {
  const cats = useApiQuery<Page<Category>>({ queryKey: (o) => qk.categories.list(o, { all: true }), path: "/categories", query: { include_disabled: true, page_size: 100 } });
  const skills = useApiQuery<Page<Skill>>({ queryKey: (o) => qk.skills.list(o, { all: true }), path: "/skills", query: { page_size: 100 } });
  const [dialog, setDialog] = useState<{ category: Category | null } | null>(null);
  const toggle = useApiMutation<Category, { id: string; is_enabled: boolean }>({
    request: (v) => ({ method: "PATCH", path: `/categories/${v.id}`, body: { is_enabled: v.is_enabled } }),
    invalidate: (o) => [qk.categories.all(o)],
    successMessage: (c) => `${c.name} ${c.is_enabled ? "enabled" : "disabled"}.`,
  });
  const columns: Column<Category>[] = [
    {
      key: "name",
      header: "Category",
      cell: (c) => (
        <span className="flex flex-col">
          <strong className="text-ink">{c.name}</strong>
          {c.description && <span className="text-[13px] text-muted">{c.description}</span>}
        </span>
      ),
    },
    { key: "dur", header: "Default duration", cell: (c) => `${c.default_duration_minutes} min` },
    {
      key: "skills",
      header: "Required skills",
      cell: (c) => (c.required_skills.length ? <span className="flex flex-wrap gap-1">{c.required_skills.map((s) => <Badge key={s.id}>{s.name}</Badge>)}</span> : <span className="text-muted">None</span>),
    },
    {
      key: "enabled",
      header: "Enabled",
      cell: (c) => (
        <span className="flex items-center gap-2">
          <Switch aria-label={`${c.name} enabled`} checked={c.is_enabled} disabled={toggle.isPending} onCheckedChange={(v) => toggle.mutate({ id: c.id, is_enabled: v })} />
          <span className="text-[13px] text-muted">{c.is_enabled ? "Enabled" : "Disabled"}</span>
        </span>
      ),
    },
    {
      key: "actions",
      header: <span className="sr-only">Actions</span>,
      className: "text-right",
      cell: (c) => (
        <Button size="sm" variant="secondary" onClick={() => setDialog({ category: c })}>
          Edit <span className="sr-only">{c.name}</span>
        </Button>
      ),
    },
  ];
  return (
    <Panel
      title="Categories"
      bodyClassName="p-0"
      actions={
        <Button size="sm" onClick={() => setDialog({ category: null })}>
          <Plus className="size-4" aria-hidden /> New category
        </Button>
      }
    >
      <DataTable caption="Categories" columns={columns} rows={cats.data?.items} rowKey={(c) => c.id} loading={cats.isLoading} error={cats.error} onRetry={() => cats.refetch()} />
      {dialog && <CategoryDialog key={dialog.category?.id ?? "new"} category={dialog.category} skills={skills.data?.items ?? []} onClose={() => setDialog(null)} />}
    </Panel>
  );
}

export function CategoriesPage() {
  return (
    <AdminPage title="Categories and skills" description="What kinds of requests exist and which skills they need.">
      <Skills />
      <Categories />
    </AdminPage>
  );
}
