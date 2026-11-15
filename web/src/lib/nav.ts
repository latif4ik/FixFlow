/**
 * ONE place for role -> navigation, role homes and route access. UX only: the backend enforces authorization.
 * Owner: W1. Feature agents must not edit; ask the lead if a route needs another role.
 */
import { Bell, Building2, CalendarDays, ClipboardList, Hammer, LayoutDashboard, ListChecks, PlusCircle, Receipt, Settings, TimerOff } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type { Role } from "@/lib/api/types";

export interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  /** "overdue" shows the overdue count from GET /dashboard/overdue. */
  badge?: "overdue";
  /** Extra path prefixes that mark this item active. */
  also?: string[];
  /** Paths that must NOT mark this item active (they belong to another item). */
  exclude?: string[];
}

export const ROLE_HOME: Record<Role, string> = {
  REQUESTER: "/requests",
  DISPATCHER: "/dashboard",
  ADMIN: "/dashboard",
  TECHNICIAN: "/jobs",
};

export const ROLE_LABEL: Record<Role, string> = {
  REQUESTER: "Requester",
  DISPATCHER: "Dispatcher",
  ADMIN: "Admin",
  TECHNICIAN: "Technician",
};

const NOTIFICATIONS: NavItem = { href: "/notifications", label: "Notifications", icon: Bell };

const STAFF_ITEMS: NavItem[] = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/queue", label: "Request queue", icon: ListChecks, also: ["/requests"] },
  { href: "/schedule", label: "Schedule board", icon: CalendarDays },
  { href: "/properties", label: "Properties and assets", icon: Building2, also: ["/assets"] },
  { href: "/estimates", label: "Estimates", icon: Receipt },
  { href: "/overdue", label: "Overdue", icon: TimerOff, badge: "overdue" },
];

export const ADMIN_SECTIONS = [
  { href: "/admin/organization", label: "Organization" },
  { href: "/admin/staff", label: "Staff" },
  { href: "/admin/categories", label: "Categories & skills" },
  { href: "/admin/technicians", label: "Technicians" },
  { href: "/admin/hours", label: "Business hours & holidays" },
  { href: "/admin/inventory", label: "Inventory" },
  { href: "/admin/maintenance", label: "Maintenance plans" },
  { href: "/admin/reports", label: "Reports" },
  { href: "/admin/audit", label: "Audit log" },
] as const;

export function navFor(role: Role): NavItem[] {
  switch (role) {
    case "REQUESTER":
      return [
        { href: "/requests", label: "My requests", icon: ClipboardList, exclude: ["/requests/new"] },
        { href: "/requests/new", label: "New request", icon: PlusCircle },
        NOTIFICATIONS,
      ];
    case "DISPATCHER":
      return [...STAFF_ITEMS, NOTIFICATIONS];
    case "ADMIN":
      return [...STAFF_ITEMS, { href: "/admin", label: "Admin", icon: Settings }, NOTIFICATIONS];
    case "TECHNICIAN":
      return [{ href: "/jobs", label: "My jobs", icon: Hammer }, NOTIFICATIONS];
  }
}

export function isNavActive(item: NavItem, pathname: string): boolean {
  if (item.exclude?.some((p) => pathname === p || pathname.startsWith(`${p}/`))) return false;
  if (pathname === item.href) return true;
  if (pathname.startsWith(`${item.href}/`)) return true;
  return (item.also ?? []).some((p) => pathname.startsWith(p));
}

const ALL: Role[] = ["REQUESTER", "DISPATCHER", "ADMIN", "TECHNICIAN"];
const STAFF: Role[] = ["DISPATCHER", "ADMIN"];

/** Roles allowed to view a path (UX gate). First matching rule wins. */
const ROUTE_RULES: { test: (p: string) => boolean; roles: Role[] }[] = [
  { test: (p) => p === "/requests" || p === "/requests/new", roles: ["REQUESTER"] },
  { test: (p) => p.startsWith("/requests/"), roles: ["REQUESTER", "DISPATCHER", "ADMIN", "TECHNICIAN"] },
  { test: (p) => p.startsWith("/notifications"), roles: ALL },
  { test: (p) => p.startsWith("/admin"), roles: ["ADMIN"] },
  { test: (p) => p.startsWith("/jobs"), roles: ["TECHNICIAN"] },
  {
    test: (p) => ["/dashboard", "/queue", "/schedule", "/properties", "/assets", "/estimates", "/overdue"].some((r) => p === r || p.startsWith(`${r}/`)),
    roles: STAFF,
  },
];

export function rolesForPath(pathname: string): Role[] {
  return ROUTE_RULES.find((r) => r.test(pathname))?.roles ?? ALL;
}
