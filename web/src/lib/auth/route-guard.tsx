"use client";

import { Lock } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import type { ReactNode } from "react";
import { Button, EmptyState, LoadingState } from "@/components/ui";
import type { Role } from "@/lib/api/types";
import { ROLE_HOME } from "@/lib/nav";
import { useAuth } from "./auth-context";

export function SessionExpired({ next }: { next?: string }) {
  const href = `/login?expired=1${next ? `&next=${encodeURIComponent(next)}` : ""}`;
  return (
    <main className="mx-auto flex min-h-[60vh] max-w-md items-center px-4">
      <EmptyState
        icon={Lock}
        title="Your session has expired"
        description="For your security you were signed out. Sign in again to continue where you left off."
        action={
          <Link href={href} className="inline-flex h-10 items-center rounded-md bg-primary px-4 text-sm font-semibold text-white hover:bg-primary-dark">
            Sign in again
          </Link>
        }
      />
    </main>
  );
}

export function Forbidden({ role }: { role: Role | null }) {
  const router = useRouter();
  return (
    <div role="alert" className="mx-auto max-w-md py-10">
      <EmptyState
        icon={Lock}
        title="You do not have access to this page"
        description="Your role in this organization does not include this area. If you need access, ask an administrator."
        action={
          <Button onClick={() => router.push(role ? ROLE_HOME[role] : "/login")} variant="secondary">
            Go to my home
          </Button>
        }
      />
    </div>
  );
}

/**
 * UX-only route guard (the backend enforces). unauthenticated -> /login?next=..., session expired -> expired screen,
 * several memberships and none selected -> /select-org, role not in `roles` -> Forbidden.
 * The (app) layout already wraps every page with `rolesForPath(pathname)`; use this directly for extra, narrower gates.
 */
export function RouteGuard({ roles, children }: { roles?: readonly Role[]; children: ReactNode }) {
  const { status, role, orgId, signedOut } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  const needsLogin = status === "unauthenticated";
  const needsOrg = status === "authenticated" && !orgId;

  useEffect(() => {
    if (needsLogin) router.replace(signedOut ? "/login" : `/login?next=${encodeURIComponent(pathname)}`);
    else if (needsOrg) router.replace(`/select-org?next=${encodeURIComponent(pathname)}`);
  }, [needsLogin, needsOrg, signedOut, router, pathname]);

  if (status === "expired") return <SessionExpired next={pathname} />;
  if (status === "loading" || needsLogin || needsOrg) return <LoadingState label="Checking your session" />;
  if (roles && (!role || !roles.includes(role))) return <Forbidden role={role} />;
  return <>{children}</>;
}
