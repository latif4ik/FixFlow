"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { Button, Dialog, FormField, FormServerError, Input, Select, Textarea } from "@/components/ui";
import type { Schemas } from "@/lib/api/types";
import { useApiMutation } from "@/lib/query/hooks";
import { qk } from "@/lib/query/keys";

type Property = Schemas["PropertyOut"];
type Asset = Schemas["AssetOut"];

const propertySchema = z.object({
  name: z.string().trim().min(1, "Enter a name").max(200, "At most 200 characters"),
  address: z.string().trim().min(1, "Enter an address").max(500, "At most 500 characters"),
  contact_instructions: z.string().max(1000, "At most 1000 characters"),
  is_active: z.boolean(),
});
type PropertyValues = z.infer<typeof propertySchema>;

export function PropertyFormDialog({ open, onOpenChange, property }: { open: boolean; onOpenChange: (o: boolean) => void; property?: Property }) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange} title={property ? `Edit ${property.name}` : "New property"} description="Properties group assets and control which requesters can submit requests.">
      {open && <PropertyForm property={property} onDone={() => onOpenChange(false)} />}
    </Dialog>
  );
}

function PropertyForm({ property, onDone }: { property?: Property; onDone: () => void }) {
  const form = useForm<PropertyValues>({
    resolver: zodResolver(propertySchema),
    defaultValues: { name: property?.name ?? "", address: property?.address ?? "", contact_instructions: property?.contact_instructions ?? "", is_active: property?.is_active ?? true },
  });
  const m = useApiMutation<Property, PropertyValues>({
    request: (v) => ({
      method: property ? "PATCH" : "POST",
      path: property ? `/properties/${property.id}` : "/properties",
      body: { name: v.name.trim(), address: v.address.trim(), contact_instructions: v.contact_instructions.trim() || null, ...(property ? { is_active: v.is_active } : {}) },
    }),
    idempotent: !property,
    invalidate: (o) => [qk.properties.all(o)],
    successMessage: property ? "Property saved." : "Property created.",
    form,
    onSuccess: onDone,
  });
  const e = form.formState.errors;
  return (
    <form noValidate className="flex flex-col gap-4" onSubmit={form.handleSubmit((v) => m.mutate(v))}>
      <FormServerError form={form} />
      <FormField label="Name" required error={e.name?.message}>
        <Input {...form.register("name")} />
      </FormField>
      <FormField label="Address" required error={e.address?.message}>
        <Input {...form.register("address")} />
      </FormField>
      <FormField label="Access / contact instructions" error={e.contact_instructions?.message} hint="Shown to technicians, e.g. check in at the front desk.">
        <Textarea rows={3} {...form.register("contact_instructions")} />
      </FormField>
      {property && (
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" className="size-4 accent-primary" {...form.register("is_active")} /> Active (inactive properties cannot receive new requests)
        </label>
      )}
      <div className="flex justify-end gap-2">
        <Button variant="secondary" onClick={onDone}>
          Cancel
        </Button>
        <Button type="submit" loading={m.isPending}>
          {property ? "Save property" : "Create property"}
        </Button>
      </div>
    </form>
  );
}

const assetSchema = z.object({
  code: z.string().trim().min(1, "Enter an asset code").max(50, "At most 50 characters"),
  name: z.string().trim().min(1, "Enter a name").max(200, "At most 200 characters"),
  asset_type: z.string().trim().min(1, "Enter a type, e.g. HVAC unit").max(100, "At most 100 characters"),
  serial_number: z.string().max(100, "At most 100 characters"),
  installed_on: z.string().refine((v) => v === "" || /^\d{4}-\d{2}-\d{2}$/.test(v), "Use a valid date"),
  status: z.enum(["ACTIVE", "OUT_OF_SERVICE", "RETIRED"]),
  notes: z.string().max(2000, "At most 2000 characters"),
});
type AssetValues = z.infer<typeof assetSchema>;

export function AssetFormDialog({ open, onOpenChange, propertyId, asset }: { open: boolean; onOpenChange: (o: boolean) => void; propertyId: string; asset?: Asset }) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange} title={asset ? `Edit ${asset.code}` : "New asset"} description="Assets are the equipment requests are filed against.">
      {open && <AssetForm propertyId={propertyId} asset={asset} onDone={() => onOpenChange(false)} />}
    </Dialog>
  );
}

function AssetForm({ propertyId, asset, onDone }: { propertyId: string; asset?: Asset; onDone: () => void }) {
  const form = useForm<AssetValues>({
    resolver: zodResolver(assetSchema),
    defaultValues: {
      code: asset?.code ?? "",
      name: asset?.name ?? "",
      asset_type: asset?.asset_type ?? "",
      serial_number: asset?.serial_number ?? "",
      installed_on: asset?.installed_on ?? "",
      status: asset?.status ?? "ACTIVE",
      notes: asset?.notes ?? "",
    },
  });
  const m = useApiMutation<Asset, AssetValues>({
    request: (v) => ({
      method: asset ? "PATCH" : "POST",
      path: asset ? `/assets/${asset.id}` : "/assets",
      body: {
        property_id: propertyId,
        code: v.code.trim(),
        name: v.name.trim(),
        asset_type: v.asset_type.trim(),
        serial_number: v.serial_number.trim() || null,
        installed_on: v.installed_on || null,
        status: v.status,
        notes: v.notes.trim() || null,
      },
    }),
    idempotent: !asset,
    invalidate: (o) => [qk.assets.all(o)],
    successMessage: asset ? "Asset saved." : "Asset created.",
    form,
    onSuccess: onDone,
  });
  const e = form.formState.errors;
  return (
    <form noValidate className="grid gap-4 sm:grid-cols-2" onSubmit={form.handleSubmit((v) => m.mutate(v))}>
      <div className="sm:col-span-2">
        <FormServerError form={form} />
      </div>
      <FormField label="Code" required error={e.code?.message}>
        <Input {...form.register("code")} />
      </FormField>
      <FormField label="Type" required error={e.asset_type?.message}>
        <Input {...form.register("asset_type")} />
      </FormField>
      <FormField label="Name" required error={e.name?.message} className="sm:col-span-2">
        <Input {...form.register("name")} />
      </FormField>
      <FormField label="Serial number" error={e.serial_number?.message}>
        <Input {...form.register("serial_number")} />
      </FormField>
      <FormField label="Installed on" error={e.installed_on?.message}>
        <Input type="date" {...form.register("installed_on")} />
      </FormField>
      <FormField label="Status" error={e.status?.message}>
        <Select {...form.register("status")}>
          <option value="ACTIVE">Active</option>
          <option value="OUT_OF_SERVICE">Out of service</option>
          <option value="RETIRED">Retired</option>
        </Select>
      </FormField>
      <FormField label="Notes" error={e.notes?.message} className="sm:col-span-2">
        <Textarea rows={3} {...form.register("notes")} />
      </FormField>
      <div className="flex justify-end gap-2 sm:col-span-2">
        <Button variant="secondary" onClick={onDone}>
          Cancel
        </Button>
        <Button type="submit" loading={m.isPending}>
          {asset ? "Save asset" : "Create asset"}
        </Button>
      </div>
    </form>
  );
}
