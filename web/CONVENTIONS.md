# Web conventions

**No new dependencies.** `package.json` and `bun.lock` are owned by W1. Everything needed is installed (Radix via `radix-ui`,
`sonner`, `recharts`, `react-hook-form`, `zod`, `lucide-react`, `date-fns`, MSW 2.x ...). Never edit them. Use `@/` for `src/`.

## Ownership (add files only inside your dirs)
| Area | Owner |
|---|---|
| `src/components/**`, `src/lib/**`, `src/test/**`, `src/app/(public)`, `src/app/layout.tsx`, `(app)/layout.tsx`, `/notifications`, `/jobs`, `/requests/[id]`, `src/features/request-detail/**`, `src/features/request-actions/registry.tsx`+`types.ts`, `src/features/auth/**`, configs | W1 (shared; do not edit) |
| `/requests`, `/requests/new`, `src/features/requester/**`, `request-actions/requester/index.ts` | W2 |
| `/queue /schedule /properties(/[id]) /assets/[id] /estimates /overdue`, `src/features/dispatch/**`, `request-actions/staff/index.ts` | W3 |
| `/dashboard`, `/admin/**`, `src/features/admin/**`, `src/features/dashboard/**` | W4 |
Placeholder pages say OWNER in a comment; replace the file contents, keep the route path. Need a shared change? Ask the lead.
Role access to routes and menus lives ONLY in `src/lib/nav.ts` (`navFor`, `rolesForPath`, `ROLE_HOME`).

## Fetching
```ts
const orgId = useOrgId();                       // from "@/lib/auth"
const q = useApiQuery<Page<RequestListItem>>({
  queryKey: (o) => qk.requests.list(o, params),  // EVERY key starts with ['org', orgId]
  path: "/requests", query: params,              // params: page, page_size, ... (see OpenAPI)
});
// q.data / q.isLoading / q.error (ApiError) -> <ErrorState error={q.error} onRetry={q.refetch}/>
```
Keys: `@/lib/query` `qk.*` (requests, notifications, dashboard, reports, schedule, estimates, properties, assets, technicians, categories,
skills, members, inventory, maintenance, org, audit). Missing one: `qk.custom(orgId, "my-feature", ...)`. Types: `@/lib/api` (`Schemas[...]`, `Page<T>`).
Direct calls (rare): `api.get/post/put/patch/delete/upload` from `@/lib/api`. Server state only via TanStack Query; never copy it to useState.
Do not use `Date.now()`/`new Date()` in render (lint); use `useNow()` from `@/lib/use-now`.

## Mutations (no full reloads, ever)
```ts
const m = useApiMutation<RequestDetail, {reason: string}>({
  request: (v) => ({ path: `/requests/${id}/cancel`, body: v }),   // method defaults to POST
  idempotent: true,                                                // fresh Idempotency-Key per call
  invalidate: (orgId) => [qk.requests.detail(orgId, id), qk.requests.all(orgId)],
  successMessage: "Request canceled.", form,                       // toast; form => 422 -> field errors
});
m.mutate(vars); m.isPending                                        // duplicate calls while pending are ignored
```
Errors toast with the server message (`errorMessage: false` for inline handling). 401 shows the session-expired screen automatically.
Live SSE events already invalidate requests/dashboard/reports/schedule/estimates/assets/my-assignments/notifications; you rarely
need polling. Do not router.refresh / location.reload.

## Forms
zod schema (mirror server limits) + `useForm({resolver: zodResolver(schema)})`; each field in `<FormField label error hint required>`
wrapping `Input | Textarea | Select` (wires id, aria-describedby, aria-invalid); `<FormServerError form={form}/>` for non-field errors;
submit `<Button type="submit" loading={m.isPending}>`. Pass `form` to `useApiMutation` (or call `applyServerErrors(form, error)`).
Destructive actions: `<ConfirmDialog reason={{minLength: 3}} onConfirm={(reason) => m.mutateAsync(...)}/>`.

## UI primitives (`@/components/ui`)
Button (primary|secondary|ghost|danger, sm|md|lg, `loading`), IconButton (aria-label required), Input, Textarea, Select (native), SelectMenu (Radix),
Checkbox, RadioGroup/RadioItem, Switch, Label, FormField, FormServerError, Dialog, ConfirmDialog, Popover*, DropdownMenu*, Tabs*, Tooltip,
`toast` (sonner), Card, Panel (title/actions), Badge, StatusBadge, PriorityBadge, SlaBadge, Money, DateTime, Avatar, Skeleton, LoadingState,
EmptyState, ErrorState, InlineNote, PageHeader (breadcrumb/actions), FilterBar, Pagination, DataTable (server paging/sort, scrolls in its own box),
AuthImage / useAuthObjectUrl. Status/SLA/priority are always icon + text. Page layout: `<PageHeader/>` then panels; the (app) layout supplies `<main>`.
Protected files (images): ONLY `AuthImage`; never a bare `<img src>` to the API.

## Format helpers (`@/lib/format`)
`formatMoney(494000) -> "4 940.00 KGS"` (amounts are integer tyiyn), `formatDateTime(iso, tz, "datetime|date|time|short")`, `formatDuration(min)`,
`formatRelative`. Components: `<Money minor/>`, `<DateTime value/>` (uses the ORG timezone from context, `useOrgTimezone()`).
Never format with the browser timezone.

## Auth, orgs, guards
`useAuth()` -> `{status, user, memberships, orgId, role, timezone, switchOrg, logout}`; `useRole()`, `useOrgId()`. The `(app)` layout already
applies `RouteGuard` using `rolesForPath`; add `<RouteGuard roles={["ADMIN"]}>` only for narrower gates. Guards are UX only.
Switching org clears the query cache and resets SSE; never keep org-specific data outside the query cache (no module-level caches, no
localStorage). Never put the token in URLs/logs.

## Design tokens
`src/styles/tokens.css` (`@theme`): colors `primary primary-dark deep primary-tint ink text muted subtle border border-border-strong surface canvas canvas-2
danger danger-dark danger-tint warning warning-dark warning-tint info`, radii `rounded-sm/md/lg/xl/pill` (8/10/12/16/999), fonts `font-heading`
(Manrope) / `font-sans` (Inter), shadows `shadow-panel shadow-pop`. Use utilities (`bg-primary text-ink border-border`), no raw hex.
Responsive: mobile first; wide tables only inside DataTable; never cause horizontal page scroll.

## Testing
Vitest + jsdom + Testing Library + MSW 2.x (Bun has no Node: MSW 3 does not intercept under Bun, hence the pin). Put tests next to code
(`*.test.ts(x)`). Helpers in `@/test/render`: `renderWithProviders(ui, {session, route, search})` (QueryClient + AuthProvider with
`fakeSession({role})` + mocked `next/navigation`; check `mockRouter` from `@/test/navigation-mock`), constants `ORG_A/ORG_B`, `membership()`.
MSW: `server.use(http.get(apiUrl("/requests"), () => HttpResponse.json(...)))`, `errorResponse(status, code, message, details)`,
`jsonHandlers({...})` from `@/test/server`; unhandled requests fail the test. Tests must assert behavior (cache refresh after a mutation,
validation messages, disabled-while-pending, role-based visibility), not just rendering. Run `bun run lint && bun run typecheck && bun run test:ci && bun run build`.
