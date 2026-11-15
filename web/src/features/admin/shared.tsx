"use client";

import type { ReactNode } from "react";
import { PageHeader } from "@/components/ui";

/** Standard admin page frame: breadcrumb back to /admin, title, optional description and actions. */
export function AdminPage({ title, description, actions, children }: { title: string; description?: ReactNode; actions?: ReactNode; children: ReactNode }) {
  return (
    <div className="flex flex-col">
      <PageHeader breadcrumb={[{ label: "Admin", href: "/admin" }, { label: title }]} title={title} description={description} actions={actions} />
      <div className="flex flex-col gap-5">{children}</div>
    </div>
  );
}

export const WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"] as const;

/** "09:00:00" -> "09:00" */
export const hhmm = (t: string) => t.slice(0, 5);
/** "09:00" -> "09:00:00" */
export const withSeconds = (t: string) => (t.length === 5 ? `${t}:00` : t);

/** Quantities come from the API as decimal strings ("40.000"). Trim trailing zeros for display. */
export function formatQty(q: string | number | null | undefined): string {
  if (q === null || q === undefined || q === "") return "-";
  const n = Number(q);
  if (Number.isNaN(n)) return String(q);
  return new Intl.NumberFormat("en-GB", { maximumFractionDigits: 3 }).format(n);
}

/** Inline, always-visible error text for a failed action (role=alert so it is announced). */
export function ActionError({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <p role="alert" className="rounded-md bg-danger-tint px-3 py-2 text-sm font-semibold text-danger-dark">
      {message}
    </p>
  );
}

export function SectionHint({ children }: { children: ReactNode }) {
  return <p className="text-[13px] text-muted">{children}</p>;
}
