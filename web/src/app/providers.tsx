"use client";

import type { ReactNode } from "react";
import { TooltipProvider, Toaster } from "@/components/ui";
import { AuthProvider } from "@/lib/auth/auth-context";
import { QueryProvider } from "@/lib/query/client";

/** Root providers: TanStack Query (cleared on org switch/logout), auth/session context, tooltips, toasts. */
export function Providers({ children }: { children: ReactNode }) {
  return (
    <QueryProvider>
      <AuthProvider>
        <TooltipProvider>{children}</TooltipProvider>
        <Toaster />
      </AuthProvider>
    </QueryProvider>
  );
}
