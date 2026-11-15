import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { RenderResult } from "@testing-library/react";
import type { ReactElement } from "react";
import { AuthProvider } from "@/lib/auth/auth-context";
import type { StoredSession } from "@/lib/auth/session";
import type { MembershipOut, Role } from "@/lib/api/types";
import { setMockRoute } from "./navigation-mock";

export const ORG_A = { id: "11111111-1111-4111-8111-111111111111", name: "Northwind", timezone: "Asia/Bishkek" };
export const ORG_B = { id: "22222222-2222-4222-8222-222222222222", name: "Ala-Too", timezone: "Asia/Bishkek" };

export function membership(role: Role, org = ORG_A): MembershipOut {
  return { membership_id: `m-${org.id}-${role}`, organization: org, role };
}

export function fakeSession(opts: { role?: Role; memberships?: MembershipOut[]; orgId?: string | null } = {}): StoredSession {
  const memberships = opts.memberships ?? [membership(opts.role ?? "DISPATCHER")];
  return {
    token: "test-token",
    expiresAt: new Date(Date.now() + 3_600_000).toISOString(),
    user: { id: "u1", email: "dispatcher@northwind.demo", full_name: "Test User" },
    memberships,
    orgId: opts.orgId === undefined ? (memberships[0]?.organization.id ?? null) : opts.orgId,
  };
}

export interface RenderOptions {
  /** Fake session; pass `null` for an unauthenticated visitor. Default: DISPATCHER in ORG_A. */
  session?: StoredSession | null;
  queryClient?: QueryClient;
  route?: string;
  search?: Record<string, string>;
}

/** Renders with QueryClient + AuthProvider(fake session) + mocked next/navigation. Returns RTL result + queryClient. */
export function renderWithProviders(ui: ReactElement, opts: RenderOptions = {}): RenderResult & { queryClient: QueryClient } {
  const queryClient = opts.queryClient ?? new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity }, mutations: { retry: false } } });
  setMockRoute(opts.route ?? "/", opts.search);
  const session = opts.session === undefined ? fakeSession() : opts.session;
  const result = render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider initialSession={session}>{ui}</AuthProvider>
    </QueryClientProvider>,
  );
  return Object.assign(result, { queryClient });
}
