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
