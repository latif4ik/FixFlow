# Product decisions: Smart Assign (conflict-aware suggested slots)

Spec: DOC-03 / WEB-09. This is the original workflow improvement of FixFlow.

## 1. The user problem
A dispatcher assigning a technician has to guess a technician and a time, submit, and find out from an error that the guess
failed: the technician overlaps another job, lacks a required skill, is off shift or on time off. Each failed attempt costs
a round trip while the request's SLA clock keeps running, and the dispatcher cannot see which technician would have worked.
Smart Assign answers "who can take this job, when, soonest" before anything is submitted.

## 2. What it does (actual behavior)
- **Endpoint** `GET /api/v1/requests/{id}/suggestions` (staff only; request must be TRIAGED, or SCHEDULED/ACCEPTED for
  reschedule mode, where the request's own assignment does not block). Query: `horizon_days` (1-31, default 14),
  `duration_minutes` (30-720, multiple of 15, default = category duration rounded up to 15), `limit` (1-20, default 5),
  and optional `from` / `to` (ISO datetimes, UTC; naive = UTC).
- **Window**: without `from`/`to` the search covers [next 15-minute boundary, now + horizon]. With them it covers
  [max(from, next boundary), to] and the slot must also END by `to`; `to` must be after `from` and at most 31 days later
  (otherwise 422). The web panel sends the dispatcher's Date + Earliest start + Latest finish (org timezone converted to UTC).
- **Candidates**: active technicians holding all skills the category requires. Per technician and local day, availability
  intervals are clipped to the window, assignments and time off are subtracted (adjacency is allowed), and the first
  slot on the 15-minute grid that fits is taken in each free gap. At most 2 non-overlapping slots per technician.
- **Ranking**: start time, then planned minutes in the next 7 days (lighter load first), then name. Every returned slot
  is re-validated with `eligibility.evaluate` before it is returned.
- **SLA flag**: each slot carries `sla.slot_ends_after_due`; the UI shows "Within SLA" / "Breaches SLA" with the margin.
- **Advisory, not a reservation**: assigning uses `POST` / `PUT /requests/{id}/assignment`, which repeats every check.
  If someone took the slot meanwhile the server answers 409 `schedule_conflict` (or 422 `technician_ineligible`); the UI
  shows "Slot just taken, refresh suggestions" with a Refresh button that re-queries.
- **Manual mode** ("Pick manually") calls `GET /requests/{id}/candidates?start_at&end_at` and lists every technician with
  the reason they are not eligible (missing skills, overlap with REQ-n, time off, outside availability).
- If the window yields nothing, the panel says so and offers "Show all suggestions" (no `from`/`to`: global earliest slots).

## 3. How to use it
1. Sign in as `dispatcher@northwind.demo` / `demo1234` (disposable demo credentials, local seed data only).
2. Open **Request queue**, filter "Unassigned" (TRIAGED), open **REQ-14 "Chiller noise in the server room"**.
3. In the **Assignment** panel stay on "Smart suggestions", set Date, Earliest start, Latest finish, click **Suggest slots**.
4. Pick a card (technician, window, SLA badge, workload) and click **Assign**. Reschedule uses the same picker.
The dashboard and /overdue panels link TRIAGED requests straight to `#assign`; SUBMITTED ones show **Triage** first.

## 4. Verification
Automated (backend, `tests/test_suggestions.py`): `test_earliest_slot_rounds_up_and_respects_tz`,
`test_weekend_time_off_and_busy_with_adjacency`, `test_slot_is_inside_availability_for_long_duration`,
`test_ranking_workload_limit_and_two_per_tech`, `test_unskilled_inactive_and_unavailable_excluded`,
`test_reschedule_mode_excludes_own_assignment`, `test_every_suggestion_is_accepted_and_taken_slot_disappears`,
`test_slot_ends_after_due_flag`, `test_permissions_state_and_validation`, `test_performance_eight_technicians_fourteen_days`,
and for the window: `test_window_params_respected_and_later_than_global_earliest`,
`test_window_in_the_past_is_clipped_to_now_and_tight_window_is_empty`, `test_window_validation_422`.
Web: `src/features/dispatch/request/assignment-panel.test.tsx` (slots + SLA text, `from`/`to` sent in UTC, Show all
without them, 409 refresh flow, manual eligibility reasons).
Manual: `docker compose up -d --build`, reset the demo (`docker compose exec -T backend python -m app.cli
reset-demo --yes-destroy-local-data`), sign in as above, use REQ-14 as in section 3. For a window on a given day call
`GET /requests/{id}/suggestions?from=2026-11-18T08:00:00Z&to=2026-11-18T12:00:00Z` (14:00-18:00 Asia/Bishkek): every
returned slot lies inside it. Then assign one and re-run: that slot is gone.

## 5. Trade-offs
1. **Advisory suggestions instead of reservations or locks.** Holding slots would need expiry, cleanup and a story for
   abandoned tabs, and would let one dispatcher block another. We accept stale suggestions and make the failure cheap:
   the assignment endpoint re-checks everything and the UI recovers with one click.
2. **Deterministic greedy ranking instead of optimization.** Earliest start, then lighter load, then name is explainable
   ("Earliest free slot", "lightest workload") and predictable. A global optimizer (balance load, travel, SLA across
   all open requests) could pack better but would be opaque and slow to build; dispatchers keep the final say.
3. **15-minute grid and at most 2 slots per technician.** The grid keeps appointments tidy and the search cheap
   (no per-slot queries: availability, time off and assignments are loaded once). Two non-overlapping alternatives per
   technician keep the list scannable; the cost is that some valid off-grid or later slots are not shown (manual mode covers them).
4. **Window filtering on the server.** The first version returned only the globally earliest slots and filtered by the
   chosen window in the browser, so a free 15:00-18:00 afternoon was reported as "No slots inside this window". Searching
   only inside `[from, to]` fixes correctness and keeps the response small; the 31-day cap bounds the work.
5. **One eligibility service as the source of truth.** Suggestions, manual candidates and the assignment endpoint all use
   `services/eligibility.py`; suggestions are additionally re-checked through `evaluate`, so a rule change cannot make
   the picker and the guard disagree.
6. **The database is the final arbiter.** A PostgreSQL gist EXCLUDE constraint on active assignments per technician makes
   double-booking impossible even under concurrent requests; application checks only exist to give friendly errors.
