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
