"use client";

import { ChevronRight } from "lucide-react";
import Link from "next/link";
import { PageHeader } from "@/components/ui";
import { ADMIN_SECTIONS } from "@/lib/nav";

const DESCRIPTIONS: Record<string, string> = {
  "/admin/organization": "Name, time zone and the SLA escalation check.",
  "/admin/staff": "Members, roles and who can sign in.",
  "/admin/categories": "Request categories, default durations and required skills.",
  "/admin/technicians": "Technician skills, weekly availability and time off.",
  "/admin/hours": "Weekly business hours and holidays.",
  "/admin/inventory": "Parts and materials, stock levels and low-stock items.",
  "/admin/maintenance": "Recurring preventive maintenance plans.",
  "/admin/reports": "SLA and operations reports with filters.",
  "/admin/audit": "Who changed what, and when.",
};

export function AdminIndex() {
  return (
    <div>
      <PageHeader title="Admin" description="Manage the organization, people, catalog and reports." />
      <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {ADMIN_SECTIONS.map((s) => (
          <li key={s.href}>
            <Link href={s.href} className="flex h-full items-center justify-between gap-3 rounded-xl border border-border bg-surface p-5 shadow-panel hover:border-primary">
              <span>
                <span className="block font-heading text-base font-bold text-ink">{s.label}</span>
                <span className="mt-1 block text-[13px] text-muted">{DESCRIPTIONS[s.href]}</span>
              </span>
              <ChevronRight className="size-5 shrink-0 text-subtle" aria-hidden />
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
