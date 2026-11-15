"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { LoadingState } from "@/components/ui";
import { useAuth } from "@/lib/auth/auth-context";
import { ROLE_HOME } from "@/lib/nav";

/** Entry: send the visitor to their role home, the org picker, or the login page. */
export default function Home() {
  const { status, role } = useAuth();
  const router = useRouter();
  useEffect(() => {
    if (status === "unauthenticated" || status === "expired") router.replace("/login");
    else if (status === "authenticated") router.replace(role ? ROLE_HOME[role] : "/select-org");
  }, [status, role, router]);
  return <LoadingState />;
}
