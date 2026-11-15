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
      return [...STAFF_ITEMS];
    case "ADMIN":
      return [...STAFF_ITEMS, { href: "/admin", label: "Admin", icon: Settings }];
    case "TECHNICIAN":
      return [{ href: "/jobs", label: "My jobs", icon: Hammer }, NOTIFICATIONS];
  }
}

/**
 * Items shown in the mobile/menu drawer. Staff and admin reach notifications through the top-bar bell on desktop,
 * so their main nav omits it; the drawer adds it back (the bell is also visible on small screens, this is a fallback).
 */
export function drawerNavFor(role: Role): NavItem[] {
  const items = navFor(role);
  return items.some((i) => i.href === NOTIFICATIONS.href) ? items : [...items, NOTIFICATIONS];
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

/**
 * Where to go after login: `next` only when this role may view it (otherwise the next user, e.g. a requester after a
 * dispatcher signed out from /schedule, would land on Forbidden), else the role home.
 */
export function landingFor(role: Role, next: string | null | undefined): string {
  if (next) {
    const path = next.split(/[?#]/)[0] ?? "";
    if (path && rolesForPath(path).includes(role)) return next;
  }
  return ROLE_HOME[role];
}

export function rolesForPath(pathname: string): Role[] {
  return ROUTE_RULES.find((r) => r.test(pathname))?.roles ?? ALL;
}
