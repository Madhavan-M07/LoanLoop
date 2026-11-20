---
name: adr
description: Write an Architecture Decision Record in docs/decisions/ for a significant technical choice (stack, boundaries, LLM vs deterministic, data model, infra, trade-offs). Use when a decision would be hard to reverse or would be questioned in an interview.
---

# Write an ADR

Decision topic: $ARGUMENTS

1. Find the next number in `docs/decisions/` (format `NNNN-kebab-title.md`).
2. Write it using this template (keep it under ~1 page):

```markdown
# NNNN. <Decision title>
Date: YYYY-MM-DD · Status: Proposed | Accepted | Superseded by NNNN

## Context
<The problem, constraints (free tier, team size, compliance), the outcome metric involved.>

## Options considered
1. <Option> — pros / cons
2. <Option> — pros / cons

## Decision
<What we chose and the main reason.>

## Consequences
<What gets easier, what gets harder, what we'll monitor, when we'd revisit.>
```

3. Link it from `CLAUDE.md` or `docs/ARCHITECTURE.md` if it changes a rule there.
