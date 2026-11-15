# FixFlow Tech - architecture notes (M1 foundation)

Flutter (stable 3.47.9), Android only. One state-management approach: **Riverpod 3
(plain providers + `Notifier`/`AsyncNotifier`, no codegen)**. Local store: **Drift (SQLite)**.
HTTP: **Dio**. Routing: **go_router**.

## Layers (lib/)
- `core/config` - `AppConfig` (compile-time `API_BASE_URL`), URL validation.
- `core/api` - `ApiClient` (Dio wrapper), `AuthInterceptor` (Bearer + `X-Org-Id`),
  `ErrorMappingInterceptor`, `ApiException`/`NetworkException` (sealed `AppException`).
- `core/auth` - models, `SessionController` (Notifier<SessionState>), `SessionStore` (Drift
  `session` row, non-secret), `TokenStore` (flutter_secure_storage), `AuthRepository`.
- `core/db` - `AppDatabase` (tables in `tables.dart`; `database.g.dart` is generated and committed).
- `core/providers.dart` - ALL app-wide providers (wiring). `core/theme`, `core/util`, `core/widgets`.
- `features/<name>/` - screens + feature providers + repositories + models (`auth`, `org`, `jobs`, `profile`).
- `app.dart` - router (`redirectFor` is a pure, tested function), `FixFlowApp`; `main.dart` bootstrap.

## Data flow
UI (ConsumerWidget) -> feature provider (`InboxController`, `jobDetailProvider`) ->
`JobsRepository` interface -> `ApiClient` -> Dio (interceptors) -> backend.
Repositories and UI only see `AppException`s, never `DioException`.
Auth context is read lazily from `sessionProvider` (token + selected org) per request, so
sign-in/out and org switches need no Dio rebuild. `dioProvider` rebuilds only when the server URL changes.

## Session / org
`SessionStatus`: bootstrapping -> signedOut | signedIn | expired. Router redirects on it.
Only TECHNICIAN memberships count (`technicianMemberships`); `resolveOrgRoute`:
none -> `/no-access`, one -> auto-selected -> `/inbox`, several -> `/select-org`.
Org switch = `SessionController.selectOrg`; data providers `watch(selectedOrgIdProvider)` so they
rebuild/refetch and no data leaks across orgs. Time is always rendered in the ORG timezone
(`core/util/formatters.dart`, `timezone` package with bundled tzdata).
Token: secure storage + in-memory in `SessionState` (never logged; `toString` omits it).
401 on an authenticated call -> `markExpired()` -> status `expired` -> sign-in screen with notice.
Sign-out/expiry call `AppDatabase.clearReadCache()` (session + cached_jobs) but NEVER touch
`pending_commands` / `pending_attachments` (queued offline work must survive).

## Global states (MOB-03)
`core/widgets/state_views.dart`: `LoadingView`, `EmptyView`, `ProblemView` (+ `describeProblem`
maps error -> offline / permission denied (403) / not found (404) / conflict (409) / generic).
Offline banner: `isOfflineProvider` = simulated || radio down (connectivity_plus) || last HTTP attempt
was a connection failure (`networkReachableProvider`). `simulateOfflineProvider` (Profile switch in
debug builds) forces offline for demos/tests.

## Database (schemaVersion 1)
`session` (single row id=1), `cached_jobs` (PK org_id+request_id; item_json, detail_json, scope),
`pending_commands` (autoinc id for ordering, unique client_command_id, org_id, request_id, type, payload_json,
status PENDING|SYNCING|CONFLICT|FAILED, attempts, last_error, next_attempt_at), `pending_attachments`
(FK client_command_id, position, local_path, mime, size, status, uploaded_file_id; unique (command, position)).
Migrations: bump `schemaVersion`, add an `onUpgrade` step (`m.createTable`/`m.addColumn`), never edit old steps.
Regenerate with `dart run build_runner build --delete-conflicting-outputs` and commit `database.g.dart`.

## Offline hooks for M2
- Implement `CachingJobsRepository implements JobsRepository` (wrap `ApiJobsRepository`, write/read `cached_jobs`
  scoped by org, fall back on `NetworkException`) and swap it in `jobsRepositoryProvider`
  (`features/jobs/jobs_providers.dart`). UI is unchanged.
- Outbox: new `features/outbox/` (repository over `pending_*`, a `SyncController` Notifier started from
  `app.dart`, triggered by `connectivityProvider`/`isOfflineProvider` going online and app start).
- Use `ApiClient.postJson` with `client_command_id`; map `ApiException.isConflict/isForbidden/isNotFound` to CONFLICT.
- `image_picker` + `path_provider` are already dependencies (copy files to app documents dir).

## Extension points for M3
- `features/jobs/job_actions.dart` -> `JobActionsSection` (clearly marked): replace the read-only list with
  controls driven by `JobDetail.allowedActions`; keep `actionLabel` for labels.
- Notifications screen/route: add a `GoRoute` in `app.dart` and an icon in `InboxScreen` app bar.
- After a successful mutation `ref.invalidate(jobDetailProvider(id))` and the inbox providers
  (`inboxProviderFor(scope)`).

## Conventions
- Single quotes, `dart format`, `flutter analyze` clean. No tokens/PII in logs.
- Providers live in `core/providers.dart` (app-wide) or `features/*/..._providers.dart`.
- Models are hand-written `fromJson` (defensive on optional fields). Status shown as icon + text
  (`core/widgets/chips.dart`), design tokens in `core/theme/app_theme.dart`.
- Fonts: platform default; no runtime font fetching, none bundled.

## Adding a screen
1. Create `features/<x>/<x>_screen.dart` (ConsumerWidget) and, if it loads data, a repository + provider
   that `watch(selectedOrgIdProvider)`.
2. Register a `GoRoute` in `app.dart` (`redirectFor` already guards signed-in/org state).
3. Render loading/empty/error via `state_views.dart`; times through `formatWindow/formatDateTime(orgTz)`.
4. Test it.

## Test patterns (test/)
- `support/harness.dart`: `baseOverrides()` (in-memory Drift, in-memory token store, mock SharedPreferences,
  connectivity stub), `FakeSession`, `FakeJobsRepository`; `support/fake_adapter.dart`: canned Dio responses;
  `support/fixtures.dart`: JSON fixtures.
- Widget tests pump `FixFlowApp` with `ProviderScope(overrides: ...)`; API tests use `ApiClient.buildDio(adapter: ...)`.
- DB tests: `AppDatabase(NativeDatabase.memory())`.
