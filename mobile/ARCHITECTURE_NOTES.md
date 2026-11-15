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

## Database (schemaVersion 2)
`session` (single row id=1), `cached_jobs` (PK org_id+request_id; item_json, detail_json, scope),
`pending_commands` (autoinc id for ordering, unique client_command_id, org_id, request_id, type, payload_json,
status PENDING|SYNCING|CONFLICT|FAILED, attempts, last_error, next_attempt_at), `pending_attachments`
(FK client_command_id, position, local_path, mime, size, status, uploaded_file_id; unique (command, position)).
v2 (M2) adds `pending_commands.user_id` (owner; legacy '' rows are never replayed) and `error_code`.
Migrations: bump `schemaVersion`, add an `onUpgrade` step (`m.createTable`/`m.addColumn`), never edit old steps.
Regenerate with `dart run build_runner build --delete-conflicting-outputs` and commit `database.g.dart`.

## Offline layer (M2)
- Read cache: `features/jobs/caching_jobs_repository.dart` wraps `ApiJobsRepository` (provider `jobsRepositoryProvider`).
  Success -> write-through to `cached_jobs` (org-scoped, `fetched_at` = synced time, history capped at 50);
  `NetworkException` -> served from cache with `stale`/`syncedAt` (UI: `StaleDataBanner`). 403/404 on detail evicts the row.
  Sign-in as a different user clears the read cache.
- Outbox: `features/outbox/`. `OutboxRepository` (enqueue NOTE in one transaction, validates jpeg/png/webp <= 10 MiB,
  copies photos to `<docs>/outbox/<command id>/<n>.<ext>`, only for cached jobs with ACTIVE assignment, not CLOSED/CANCELED).
  `OutboxSyncEngine` (pure Dart, single-flight): per command upload photos (`client_command_id` + `client_index`, file id
  persisted at once) then POST note with the same `client_command_id`. 200 replay == 201 -> delete. Network/5xx/429 -> PENDING,
  attempts+1, backoff 5s..5min with jitter. 401 -> stop, queue kept. 403/404/409/other 4xx -> CONFLICT (reason + `error_code`),
  never auto-deleted; user chooses Copy text / Retry / Discard (confirm). FIFO per request; only current user + org.
- `SyncController` (watched from `FixFlowApp`): app start (SYNCING->PENDING), reconnect, simulate-offline off, sign-in/org switch,
  manual Retry, 30 s timer while items wait. Sync is gated on `canSyncNow` (dev switch + radio), NOT `networkReachableProvider`.
- Offline gate for online-only actions (MOB-08): `core/widgets/requires_connection.dart` (`RequiresConnection`, `RequiresConnectionLabel`),
  state = `isOfflineProvider`. Never fake an action locally.
- Tests: `test/outbox_test.dart`, `caching_and_migration_test.dart`, `outbox_ui_test.dart`, `sync_controller_test.dart`;
  live (needs backend): `LIVE_API_URL=http://localhost:8000 flutter test test/live` (writes demo data; run `reset-demo` after).

## Technician actions, materials, notifications (M3)
- `features/jobs/job_actions.dart` `JobActionsSection`: buttons from `allowed_actions` (accept, start, resume, complete, block, decline,
  add_note). Every online-only button is wrapped in `RequiresConnection`; one action in flight at a time (double-tap safe); UI changes only
  after a 2xx, errors show a dialog with the server message (`actionErrorMessage`), then `refreshJobData` (detail + inbox providers).
  Decline/block/resume ask for a reason/note (>= 5 chars). Start disabled with `start_blocked_reason` (inbox item) when the estimate is not approved.
- `complete_job_screen.dart`: note >= 20 chars (live counter) + >= 1 photo (jpeg/png/webp <= 10 MiB, validated before upload). Each photo uploads as
  COMPLETION with its own `client_command_id` kept until success (retry replays, never duplicates), then POST /complete. A failed complete keeps
  uploaded photos (they are attached server-side) and says so. `PhotoPicker` seam (`photoPickerProvider`) lets tests/integration inject files.
- `job_materials.dart`: usage list + "Record material" sheet (IN_PROGRESS + `complete` allowed). `client_command_id` generated when the sheet opens;
  after a timeout the inputs lock and Retry resends the identical payload; a definitive 4xx rotates the id. `insufficient_stock` shows `available`.
- `job_actions_repository.dart` (`jobActionsRepositoryProvider`): the only place that calls the mutating endpoints.
- `features/notifications/`: repository, `unreadCountProvider`, list screen (`/notifications`), `NotificationsBell` (badge; owns the 60 s poll timer,
  skipped while backgrounded / radio down / dev-offline). `features/profile/availability*.dart`: read-only `/technicians/me` (`/availability`).
- Lifecycle: `FixFlowApp` observes resume and invalidates inbox, job details, unread count, notifications, availability. While the last request failed
  but the radio is up, a 15 s probe (`probeServer`, GET /health/live) and a banner "Retry" let the app leave "offline" by itself.
- Cache fix found on-device: pruning a scope no longer deletes a row that has cached detail (job moved ACCEPTED -> IN_PROGRESS must still open offline);
  only its list entry (`item_json`) is cleared.
- Tests: `test/m3_*_test.dart` (support: `test/support/m3_*.dart`; real file IO in widget tests needs `settleIo`), `integration_test/app_flow_test.dart`.

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
