---
name: feature
description: Outcome-first workflow for building any LoanLoop feature end to end (outcome → plan → build → verify → review → log). Use when starting a new feature or significant change.
---

# Build a feature, outcome first

Feature request: $ARGUMENTS

1. **Outcome gate.** Name the metric it moves (O1–O6 in CLAUDE.md) and how we'd see it move. If none applies, stop and tell the human why, with a suggested alternative.
2. **Explore.** Read the relevant code, rules and ADRs. List the files that will change.
3. **Plan** (show it to the human before coding if it touches more than ~3 files or any schema/API/MCP contract):
   - Data flow and service boundaries
   - LLM vs deterministic split, with the reason
   - Failure modes and how each one is handled
   - Verification plan: which tests and evals prove it works
   - Can it be split for parallel agents (non-overlapping areas, on `main`)?
4. **Branch:** `feat/<short-name>`.
5. **Build in small steps.** Write tests alongside the code, starting with failing tests for rules and bug fixes.
6. **Verify with evidence.** Run tests, lint, typecheck, and evals if LLM behavior changed. Paste the real output. Use the `verifier` agent for a fresh-eyes run.
7. **Review.** Run the `code-reviewer` agent; add `security-auditor` if it touches documents, PII, MCP, auth or prompts. Fix findings or justify them.
8. **Record.** ADR if a significant decision was made (`/adr`); `/build-log` entry; update `docs/ROADMAP.md` checkboxes.
9. **Report** to the human: outcome moved, what changed, evidence, risks, next step. Don't commit unless asked.
