"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, useSyncExternalStore } from "react";
import type { ReactNode } from "react";
import { api, apiAuth } from "@/lib/api";
import type { LoginResponse, MembershipOut, Role, UserBrief } from "@/lib/api";
import { ROLE_HOME } from "@/lib/nav";
import { clearStoredSession, loadSession, saveSession } from "./session";
import type { StoredSession } from "./session";

export type AuthStatus = "loading" | "authenticated" | "unauthenticated" | "expired";

export interface AuthContextValue {
  status: AuthStatus;
  user: UserBrief | null;
  memberships: MembershipOut[];
  /** Selected membership (org + role) or null when none selected yet. */
  membership: MembershipOut | null;
  orgId: string | null;
  orgName: string | null;
  /** IANA timezone of the selected org. */
  timezone: string;
  role: Role | null;
  /** Stores the login response. Returns the path to navigate to (role home or /select-org). */
  completeLogin: (res: LoginResponse) => string;
  /** Explicit org switch: clears cached server state, resets live connection, goes to the role home. */
  switchOrg: (orgId: string) => void;
  logout: () => Promise<void>;
  markExpired: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

function homeFor(m: MembershipOut): string {
  return ROLE_HOME[m.role];
}

interface StoreState {
  status: AuthStatus;
  session: StoredSession | null;
}

/** Small external store so hydration from sessionStorage does not need setState-in-effect. One per provider. */
function createAuthStore(initial?: StoredSession | null) {
  let state: StoreState =
    initial === undefined ? { status: "loading", session: null } : initial ? { status: "authenticated", session: initial } : { status: "unauthenticated", session: null };
  const listeners = new Set<() => void>();
  if (initial) apiAuth.set({ token: initial.token, orgId: initial.orgId });
  return {
    get: () => state,
    subscribe(fn: () => void) {
      listeners.add(fn);
      return () => listeners.delete(fn);
    },
    set(next: StoreState) {
      state = next;
      listeners.forEach((l) => l());
    },
  };
}

export function AuthProvider({ children, initialSession }: { children: ReactNode; initialSession?: StoredSession | null }) {
  const queryClient = useQueryClient();
  const router = useRouter();
  const [store] = useState(() => createAuthStore(initialSession));
  const { status, session } = useSyncExternalStore(store.subscribe, store.get, store.get);

  useEffect(() => {
    if (initialSession !== undefined) return;
    const stored = loadSession();
    if (stored) {
      apiAuth.set({ token: stored.token, orgId: stored.orgId });
      store.set({ status: "authenticated", session: stored });
    } else {
      store.set({ status: "unauthenticated", session: null });
    }
  }, [initialSession, store]);

  const markExpired = useCallback(() => {
    if (store.get().status !== "authenticated") return;
    // Drop the token and every cached tenant record immediately.
    clearStoredSession();
    apiAuth.clear();
    queryClient.clear();
    store.set({ status: "expired", session: null });
  }, [store, queryClient]);

  useEffect(() => {
    apiAuth.setUnauthorizedHandler(markExpired);
    return () => apiAuth.setUnauthorizedHandler(null);
  }, [markExpired]);

  const completeLogin = useCallback(
    (res: LoginResponse) => {
      queryClient.clear();
      const only = res.memberships.length === 1 ? res.memberships[0] : undefined;
      const next: StoredSession = {
        token: res.token,
        expiresAt: res.expires_at,
        user: res.user,
        memberships: res.memberships,
        orgId: only ? only.organization.id : null,
      };
      saveSession(next);
      apiAuth.set({ token: next.token, orgId: next.orgId });
      store.set({ status: "authenticated", session: next });
      return only ? homeFor(only) : "/select-org";
    },
    [queryClient, store],
  );

  const switchOrg = useCallback(
    (orgId: string) => {
      const cur = store.get().session;
      if (!cur) return;
      const m = cur.memberships.find((x) => x.organization.id === orgId);
      if (!m) return;
      // Order matters: stop everything bound to the old org before the new one is visible.
      void queryClient.cancelQueries();
      queryClient.clear();
      const next = { ...cur, orgId };
      saveSession(next);
      apiAuth.set({ orgId });
      store.set({ status: "authenticated", session: next });
      router.push(homeFor(m));
    },
    [store, queryClient, router],
  );

  const logout = useCallback(async () => {
    try {
      await api.post("/auth/logout");
    } catch {
      /* the session may already be invalid; clear locally regardless */
    }
    clearStoredSession();
    apiAuth.clear();
    queryClient.clear();
    store.set({ status: "unauthenticated", session: null });
    router.push("/login");
  }, [store, queryClient, router]);

  const value = useMemo<AuthContextValue>(() => {
    const membership = session?.memberships.find((m) => m.organization.id === session.orgId) ?? null;
    return {
      status,
      user: session?.user ?? null,
      memberships: session?.memberships ?? [],
      membership,
      orgId: membership?.organization.id ?? null,
      orgName: membership?.organization.name ?? null,
      timezone: membership?.organization.timezone ?? "UTC",
      role: membership?.role ?? null,
      completeLogin,
      switchOrg,
      logout,
      markExpired,
    };
  }, [session, status, completeLogin, switchOrg, logout, markExpired]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}

/** Selected org id; throws when none (only call inside guarded routes). */
export function useOrgId(): string {
  const { orgId } = useAuth();
  if (!orgId) throw new Error("No organization selected");
  return orgId;
}

/** Selected org timezone (IANA). */
export function useOrgTimezone(): string {
  return useAuth().timezone;
}

export function useRole(): Role {
  const { role } = useAuth();
  if (!role) throw new Error("No role: no organization selected");
  return role;
}
