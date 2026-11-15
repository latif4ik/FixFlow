# Request action registry

The shared request detail page (`/requests/[id]`, owner W1) renders role-specific panels and buttons from
registration maps, so W2/W3 never edit shared files.

| Map | File | Owner | Roles |
|---|---|---|---|
| `requesterActions` | `requester/index.ts` | W2 | REQUESTER |
| `staffActions` | `staff/index.ts` | W3 | DISPATCHER, ADMIN, TECHNICIAN |

## Add an action or panel
1. Create the component under YOUR feature dir (`src/features/requester/**` or `src/features/dispatch/**`).
   It receives `{ ctx }: RequestActionProps` with `ctx.detail` (RequestDetail), `ctx.orgId`, `ctx.role`, `ctx.timezone`, `ctx.allowed`.
2. Append a definition to your map:

```ts
import { SmartAssignPanel } from "@/features/dispatch/smart-assign-panel";
export const staffActions: RequestActionDefinition[] = [
  { name: "assign", label: "Assignment", component: SmartAssignPanel, placement: "sidebar", order: 10 },
];
```

- `name`: must equal an entry of `detail.allowed_actions` (the server's list: e.g. `assign`, `reschedule`, `unassign`, `cancel`, `triage`)
  so it only shows when permitted. Check a real response for the exact strings.
- `placement`: `"header"` (buttons beside the title), `"sidebar"` (right column panels), `"main"` (main column, above messages).
- `when: "always"` or `show(ctx)` to render a panel even when the action is not currently allowed (e.g. explain why).
- `order`: lower renders first (default 100). `roles`: optional narrowing.

## Mutations inside a panel
Use `useApiMutation` and invalidate `qk.requests.detail(orgId, id)` (+ `qk.requests.all(orgId)`); the detail page refetches
and the new `allowed_actions` re-evaluate the registry. Never `router.refresh()` / `location.reload()`.
Each panel is wrapped in an error boundary, so a crash in one panel does not take down the page.
