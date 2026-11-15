"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/lib/auth/auth-context";
import { cn } from "@/lib/cn";
import { useApiQuery } from "@/lib/query/hooks";
import { qk } from "@/lib/query/keys";
import { drawerNavFor, isNavActive, navFor } from "@/lib/nav";
import type { NavItem } from "@/lib/nav";

function useOverdueCount(enabled: boolean): number | null {
  const q = useApiQuery<{ count: number }, number>({
    queryKey: (orgId) => qk.dashboard.overdueCount(orgId),
    path: "/dashboard/overdue",
    query: { page: 1, page_size: 1 },
    select: (d) => d.count,
    enabled,
  });
  return q.data ?? null;
}

export function useNavItems(withNotifications = false): { items: NavItem[]; overdue: number | null } {
  const { role } = useAuth();
  const items = role ? (withNotifications ? drawerNavFor(role) : navFor(role)) : [];
  const overdue = useOverdueCount(items.some((i) => i.badge === "overdue"));
  return { items, overdue };
}

export function NavLinks({ orientation = "horizontal", onNavigate, withNotifications = false }: { orientation?: "horizontal" | "vertical"; onNavigate?: () => void; withNotifications?: boolean }) {
  const pathname = usePathname();
  const { items, overdue } = useNavItems(withNotifications);
  return (
    <ul className={cn("flex gap-1", orientation === "vertical" ? "flex-col" : "items-center")}>
      {items.map((item) => {
        const active = isNavActive(item, pathname);
        const Icon = item.icon;
        return (
          <li key={item.href} className="shrink-0">
            <Link
              href={item.href}
              onClick={onNavigate}
              aria-current={active ? "page" : undefined}
              className={cn(
                "flex items-center gap-2 whitespace-nowrap rounded-md px-2.5 py-2 text-sm font-semibold transition-colors",
                active ? "bg-primary-tint text-primary-dark" : "text-text hover:bg-canvas-2",
              )}
            >
              <Icon className="size-4 shrink-0" aria-hidden />
              {item.label}
              {item.badge === "overdue" && overdue !== null && overdue > 0 && (
                <span className="ml-0.5 rounded-pill bg-danger px-2 py-0.5 text-xs font-bold text-white" aria-label={`${overdue} overdue`}>
                  {overdue}
                </span>
              )}
            </Link>
          </li>
        );
      })}
    </ul>
  );
}
