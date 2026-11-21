# LoanLoop Build Log

An honest record of how this was built with AI agents: what the agents did, what the human decided and fixed, and what broke. Newest at the bottom. Add entries with `/build-log`.

## 2026-11-20 — Claude Code project setup
**Outcome:** Infrastructure for all outcomes (O1–O6). Makes every later agent run repo-aware and verifiable.
**Agents used:** Claude Code (main session).
**What the agents did:** Turned the job requirements and the outcome-first product direction into the following:
- `CLAUDE.md`
- 8 path-scoped rules
- 6 skills (feature, adr, build-log, add-eval, mcp-tool, ship-check)
- 5 subagents (architect, code-reviewer, security-auditor, test-engineer, verifier)
- Python hooks: bash/file guards, auto-format + lint, verify-on-stop, session context
- project MCP servers (context7 docs, Playwright)
- this roadmap and log

**What the human did/fixed:** Chose the target domain (mortgage lending, matching Confer Solutions' customers) and insisted on an outcome-based, work-backwards approach. *(add your own notes)*
**What broke & how it was fixed:** Hooks activated the moment `.claude/settings.json` was written, before the hook scripts existed, so the PostToolUse hook failed with "No such file". Fix: the scripts were created right after. Lesson: write the hook scripts first, then register them in settings.
A second issue came from testing rather than being trusted: the smoke tests showed that the guard meant to stop writes to `evals/data/real/` (real borrower data) **silently allowed them**.
- Root cause: Git Bash reports the project dir as `/c/Users/...`, while tools pass `C:/Users/...`, so the relative-path check never matched.
- Fix: normalize MSYS paths in `_common.py`, and match the protected folder anywhere in the path.
- Re-test: the write is now denied.

Separately, the Bash guard blocked the agent's own test command (it contained the text `rm -rf /`). That was correct behavior, so the tests were moved into a script file.
**Evidence:** 11 hook smoke tests (deny/ask/allow cases) all behave as expected after the fix; settings.json and .mcp.json parse as valid JSON.
**Lesson:** Order matters when agents configure their own guardrails.

## 2026-11-21 — Work on main + CI safety net
**Outcome:** Infrastructure for all outcomes (O1–O6): keeps `main` deployable now that there are no PRs.
**Agents used:** Claude Code (main session).
**What the agents did:**
- Fast-forwarded `main` to `feat/agent-core`, committed the pending pipeline work (per-loan lock against duplicate drafts; `SEND_FAILED` status so failed sends return to the inbox) and the rules work (newer documents supersede expired ones), and pushed.
- Updated `CLAUDE.md`, the git-workflow rule, the `/feature` skill and the `architect` agent to "all work on `main`".
- Added `.github/workflows/ci.yml`: secret scan (project scanner + gitleaks over full history), ruff lint + format check, mypy, backend tests (incl. the layer-architecture contract), scanner tests.
- Enabled the pydantic mypy plugin (6 false `Settings` errors) so type checking could run in CI.

**What the human did/fixed:** Decided to drop feature branches and PRs and work directly on `main`; chose CI as the one thing to finish first.
**What broke & how it was fixed:** The first CI run failed. Locally, ruff had only been run from `backend/`; CI runs it from the repo root, which also covers `.claude/hooks/` (6 unformatted files, 3 lint issues). The local pre-push check missed it because `cmd | tail -1` swallowed ruff's exit code inside an `&&` chain. Fix: formatted the hooks, wrapped 2 long strings, justified one `S603` noqa, smoke-tested the guards, and re-ran every CI step under `set -e -o pipefail` before pushing.
**Evidence:** CI run 44879056206 on `46475ca`: Secret scan ✅, Backend (lint, format, types, tests) ✅. Locally: mypy clean (30 files), backend 106 passed, scanner 23 passed.
**Lesson:** Run checks exactly the way CI runs them (same directory, failures not hidden by pipes), or CI is the first place they really run.

## 2026-11-21 — PostgreSQL storage (steps 1–4)
**Outcome:** Infrastructure for O1–O6: loan files now survive restarts, which a real processor needs before anything else. O2 and O6 can't even be measured without durable history.
**Agents used:** Claude Code (main session).
**What the agents did:**
- Step 1: Postgres 16 in Docker (127.0.0.1 only), `/health` reports the database, SQLAlchemy async + asyncpg.
- Step 2: ADR 0002 (hybrid schema), 7 tables, Alembic migration 0001. The database itself enforces no duplicate open drafts (partial unique index), an append-only audit log (trigger), and valid enum values. Adminer browser viewer at http://localhost:8080.
- Step 3a: storage interface (`Repository`/`Session`). The in-memory store returns copies, so a missing save fails in tests exactly as it would in Postgres. All 126 existing tests passed with zero test edits.
- Step 3b: `PostgresRepository` (one session = one transaction, `FOR NO KEY UPDATE` loan lock). Every store-based test now runs on memory AND Postgres, each Postgres test on a database cloned from a seeded template.
- Step 3c: the app uses Postgres when configured; prod refuses to start without a database; add-only demo loader (`python -m app.data.seed`); audit rows record before → after.
- Step 4: CI starts a Postgres service; a guard makes pytest refuse to run in CI if database tests would skip.

**What the human did/fixed:** Approved ADR 0002. Chose local Postgres now and hosted (Oracle VPS or Neon) at deploy time. Fixed the expired Docker Hub login. Set the order: finish storage, then the frontend, then the other layers.
**What broke & how it was fixed:**
- Migration used status `'pending'`; the domain stores `'pending_approval'`. Every real draft would have been rejected and the duplicate-draft index would never apply. A test comparing DB values to domain enums caught it; another test now ties the index to `OPEN_DRAFT_STATUSES`.
- Constraint names were doubled (`ck_loans_ck_loans_stage`) by the naming convention. Fixed with `op.f()`.
- `localhost` cost ~2 s per connection on Windows (IPv6 first). Using `127.0.0.1` cut the DB suite from 146 s to 15 s.
- **Security:** pydantic config errors echoed input values, so a refused config printed the tail of a real key from a developer's env file. Fixed with `hide_input_in_errors=True` plus a regression test; the human was asked to rotate the key.
- An inline shell command hung (a stray `cat >` waiting for input) and a shell quoting error; both were redone with file edits. The project's own Bash guard blocked a command containing the text ".env", which was correct behaviour.

**Evidence:** 184 tests pass (memory + Postgres), 0 skipped in CI (run 44909042883 on `7b90632`). Sabotage checks with the lock disabled: the double-approval and lock-ordering tests fail on Postgres as they should. A real uvicorn server kept an uploaded paystub and its draft across a restart.
**Lesson:** Verify tests by breaking the thing they guard. The double-approval test passed in memory even without the lock, and only Postgres showed it was meaningful.

## 2026-11-21 — Processor dashboard (frontend)
**Outcome:** O1/O5 (one place to see and act on files), O4 (approve borrower requests fast), O6 (the evidence behind every AI value is visible).
**Agents used:** Claude Code (main session), with Playwright MCP for the browser check.
**What the agents did:**
- Next.js 15 + Tailwind, server components. Screens: loan queue (+ stuck filter), loan file (required docs, rule checks, extracted fields with source snippets or "verify manually", AI confidence, approval, audit timeline with before → after), approval inbox, borrower upload simulator with synthetic documents.
- Dev sign-in with demo users; the token lives in an httpOnly cookie and the API is called only from the server.
- API client and types generated from the backend's OpenAPI schema; CI fails if either is stale.
- Backend: evidence returned to human processors only (agents and the assistant never get raw document text). Loan file documents are now typed.
- CI: a frontend job (lint, typecheck, Vitest, build).

**What the human did/fixed:** Asked for the frontend before more backend layers so the product can be seen and debugged. Chose the first screens.
**What broke & how it was fixed:**
- The first draft hand-wrote API types and used browser storage, which violates the project's frontend rules. It was replaced with generated types and server-side calls before anything was built on it.
- Evidence was missing from the loan file API on purpose: the assistant reuses it and must not send raw document text to an outside LLM. Fixed with a human-only flag instead of exposing it to everyone.
- Ports 3000/8000 were held by other local programs; the check ran on 3011/8011. A shared `.next` build folder caused `__webpack_require__.n is not a function`; `NEXT_DIST_DIR` now gives each instance its own folder.
- Lint failed (it was linting build output) while the script printed ALL_PASS, because `npm.cmd` didn't propagate the exit code through a pipe. Exit codes are now checked explicitly.
- The scaffold's `.gitignore` ignored `.env.example`; fixed.
- The final "Approve & send" click was blocked by the agent's permission policy (it sends a borrower message). Correct: left for the human.

**Evidence:** CI run 44930951949 on `6280603`: frontend, backend (190 tests incl. Postgres), secret scan all green. Browser: borrower upload → paystub extracted; agent approval refused ("a human must"); processor sees only own brokerage; loan file shows evidence and 95% confidence.
**Lesson:** Read the path-scoped rules before writing the first file. Two of three frontend rules were only noticed after the first draft.
