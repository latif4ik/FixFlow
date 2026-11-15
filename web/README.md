# FixFlow web

Next.js 16 (App Router, React 19, TypeScript strict), Tailwind CSS v4, TanStack Query. Bun for install and scripts.
Client-rendered app: no tenant data is rendered on the server or cached by Next.

## Develop
```bash
bun install
bun run dev            # http://localhost:3000 (API at http://localhost:8000)
```
Sign in with a demo account (password `demo1234`), e.g. `dispatcher@northwind.demo`, `requester1@northwind.demo`, `admin@northwind.demo`.

## Scripts
| Script | What it does |
|---|---|
| `bun run lint` | `eslint .` (Next + TypeScript + React Compiler rules) |
| `bun run typecheck` | `tsc --noEmit` (strict, `noUncheckedIndexedAccess`) |
| `bun run test:ci` | Vitest + jsdom + Testing Library + MSW, single run |
| `bun run build` | production build (standalone output) |
| `bun run gen:api` | regenerate `src/lib/api/schema.d.ts` from the running API's OpenAPI |

## Environment
- `NEXT_PUBLIC_API_URL` (default `http://localhost:8000`): API base URL as seen by the browser. Build-time for Docker.
- Compose: `WEB_PORT` (default 3000). If you change it, add the origin to the backend `CORS_ORIGINS`.

## Docker
`docker compose up -d --build web` from the repo root (the `web` service waits for a healthy backend).

Team conventions (folders, data fetching, forms, UI primitives, tests): see [CONVENTIONS.md](./CONVENTIONS.md).
