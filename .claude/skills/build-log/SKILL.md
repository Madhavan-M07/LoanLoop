---
name: build-log
description: Append an honest entry to docs/BUILD_LOG.md recording what AI agents did, what the human built or fixed, and what broke and how it was fixed. Use after finishing a task, a debugging session, or a parallel-agent run.
---

# Add a build-log entry

This log is evidence for job applications ("what did the agents do, what did you fix, what broke"). Be specific and honest. Never inflate.

Append to `docs/BUILD_LOG.md` (newest at the bottom) using this format:

```markdown
## YYYY-MM-DD — <short title>
**Outcome:** O<n> — <metric it moves>
**Agents used:** <e.g. Claude Code main + 3 subagents in worktrees (backend, frontend, tests); Codex PR review>
**What the agents did:** <concrete: files/modules generated, tests written, reviews found X>
**What the human did/fixed:** <decisions made, code corrected, bugs the agents missed>
**What broke & how it was fixed:** <symptom → root cause → fix → test that now guards it>
**Evidence:** <test counts, eval accuracy before→after, PR link, commit>
**Lesson:** <one line, what we'd do differently with agents next time>
```

Context for this entry: $ARGUMENTS

Ask the human to fill in "What the human did/fixed" if you don't know it; don't guess.
