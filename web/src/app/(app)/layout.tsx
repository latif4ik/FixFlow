"use client";

import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { TopBar } from "@/components/shell";
import { RouteGuard } from "@/lib/auth/route-guard";
import { LiveUpdatesProvider } from "@/lib/live";
import { rolesForPath } from "@/lib/nav";

/**
 * Authenticated shell for every signed-in page: session guard + role gate (from lib/nav.ts), top bar, live updates.
 * Pages render only inside <main>; they never need their own guard unless they want a narrower one.
 */
export default function AppLayout({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  return (
    <RouteGuard>
      <LiveUpdatesProvider>
        <TopBar />
        <main id="main" className="mx-auto w-full max-w-[1440px] px-4 py-6 sm:px-6">
          <RouteGuard roles={rolesForPath(pathname)}>{children}</RouteGuard>
        </main>
      </LiveUpdatesProvider>
    </RouteGuard>
  );
}
