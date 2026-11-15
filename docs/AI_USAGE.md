# AI usage

Covers DOC-06. This project was built with AI coding assistants, directed and reviewed by the author. Prompts and full
chat logs are not included.

## Tools

| Tool | Role |
|---|---|
| **Claude Code** (Anthropic CLI) with **Claude Opus** as the lead model | Planned each area with the author, wrote `PLAN.md` (data model, decisions, phases, handoff notes), wrote task briefs, reviewed and verified every phase, ran the real-browser walkthrough, fixed bugs found. |
| **Claude Sonnet** subagents (via Claude Code) | Implemented the delegated phases (backend areas, web screens W2-W5, mobile steps M1-M3, these docs), several in parallel git worktrees that were merged after review. |
| **Claude Design** (artifact canvas) | The author used it to design the Day plan and Request detail / Smart Assign screens; the web implementation follows those two designs. |

No other generation tools were used. Existing open-source libraries (FastAPI, SQLAlchemy, Next.js, TanStack Query,
Riverpod, Drift, etc.) are used under their licenses (TECH-08).

## Division of work

- **Human (author):** decided the architecture and scope, reviewing the options the lead proposed area by area (for
  example PostgreSQL constraints as the source of truth, and building web before mobile), the priorities for the
  one-day build, the original feature (Smart Assign) and its trade-offs, the visual design direction, and every go/no-go
  on a phase.
- **Lead model:** turned those decisions into `PLAN.md`, decomposed work into phases with acceptance criteria, and
  reviewed results against the spec requirements (the requirement ids such as SCHED-04 or INV-05 are referenced in code
  comments and tests).
- **Subagents:** wrote code and tests for one bounded phase at a time against the written plan and conventions
  (`web/CONVENTIONS.md`, `mobile/ARCHITECTURE_NOTES.md`).

## How AI output was verified

1. **Automated gates on every phase:** `ruff check`, `ruff format --check`, `ty check`, `pytest`; web `eslint`, `tsc`,
   Vitest, `next build`; mobile `dart format`, `flutter analyze`, `flutter test`, APK build. The lead re-ran these
   itself rather than trusting a subagent's report. The combined command is `scripts/verify-all.sh`.
2. **Tests that fail on wrong behavior,** not placeholders: concurrency tests use real parallel transactions against
   PostgreSQL (assignment overlap, last-unit stock, replay), and migrations are checked against the models.
3. **Real HTTP checks:** `scripts/smoke.sh` (positive lifecycle plus 401/403/404/409 failures) and
   `scripts/simulate_race.py` (parallel requests against the running stack).
4. **Real-browser walkthrough by the lead** of the dashboard, queue, Smart Assign on REQ-14, schedule day/week,
   requester approval on REQ-8, new-request validation, phone width, organization switching and admin inventory/audit,
   plus a live emulator test of the Android offline queue (duplicate delivery produced exactly one note and one
   attachment).
5. **Spec traceability:** requirement ids were re-read against the implementation; gaps were recorded in
   [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) instead of being marked complete.

### Examples of defects found by review and fixed

Browser inspection found issues that automated tests had not caught:

- The triage **category select showed the first option** instead of the request's category (uncontrolled select).
- **Navigation labels were truncated** at common widths (the nav now collapses to a drawer below 1536 px).
- Smart Assign **suggestions ignored the dispatcher's time window** (earliest start / latest finish); backend and web
  were changed so slots must start and end inside it.
- Smaller items from the same review: week-grid misalignment, a sign-out `?next` redirect bug, a raw
  `Awaiting_approval` label, missing technician/appointment columns in the queue.

## What AI did not decide

Product direction, data-isolation approach, which requirements to cut or defer, and acceptance of each phase remained
with the author. AI-written code was treated as untrusted until it passed the checks above.
