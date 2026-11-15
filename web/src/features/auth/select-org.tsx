"use client";

import { Building2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { Card, LoadingState } from "@/components/ui";
import { useAuth } from "@/lib/auth/auth-context";
import { ROLE_LABEL } from "@/lib/nav";

export function SelectOrg() {
  const { status, memberships, orgId, switchOrg } = useAuth();
  const router = useRouter();
  useEffect(() => {
    if (status === "unauthenticated") router.replace("/login");
  }, [status, router]);
  if (status === "loading" || status === "unauthenticated") return <LoadingState />;
  return (
    <Card className="w-full max-w-md p-6 sm:p-8">
      <h1 className="text-2xl font-extrabold">Choose an organization</h1>
      <p className="mt-1 text-sm text-muted">Your account belongs to several organizations. You can switch any time from the top bar.</p>
      <ul className="mt-5 flex flex-col gap-2">
        {memberships.map((m) => (
          <li key={m.membership_id}>
            <button
              type="button"
              onClick={() => switchOrg(m.organization.id)}
              aria-current={m.organization.id === orgId ? "true" : undefined}
              className="flex w-full items-center gap-3 rounded-lg border border-border bg-surface p-3 text-left hover:border-primary hover:bg-primary-tint/40"
            >
              <Building2 className="size-5 text-primary" aria-hidden />
              <span>
                <span className="block font-semibold text-ink">{m.organization.name}</span>
                <span className="block text-[13px] text-muted">{ROLE_LABEL[m.role]}</span>
              </span>
            </button>
          </li>
        ))}
      </ul>
    </Card>
  );
}
