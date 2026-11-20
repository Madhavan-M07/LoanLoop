---
name: ship-check
description: Production-readiness checklist before deploying LoanLoop to the VPS via Docker/Coolify. Use before any deploy or release; reports pass/fail with evidence and never deploys by itself.
---

# Ship check

Run every check and report a table: check | pass/fail | evidence. **Do not deploy.** Deploying is outward-facing, so hand the result to the human.

**Correctness**
- [ ] All test suites green (backend, mcp, frontend); paste the summary lines
- [ ] Evals at or above the last accepted accuracy
- [ ] Alembic migrations apply cleanly on a fresh DB and are reversible

**Security**
- [ ] No secrets in the repo (`git grep -nE "(api[_-]?key|secret|token|password)\s*[:=]"` reviewed)
- [ ] `.env.example` lists every required variable
- [ ] `security-auditor` run on changes since last release; no open high-severity findings
- [ ] Containers run as non-root; only the reverse proxy port is exposed; HTTPS on

**Operability**
- [ ] `/health` and `/ready` endpoints; Docker healthchecks configured
- [ ] Structured logs with PII masked; Langfuse tracing on
- [ ] Postgres backup job configured, and a restore was tested once
- [ ] Rollback steps written in `infra/RUNBOOK.md`
- [ ] Resource limits fit the free VPS (memory per container)

**Product**
- [ ] The demo flow works end to end on staging: upload → extract → checks → borrower chase → processor approval
- [ ] The outcome metrics dashboard shows real (synthetic-run) numbers

Context: $ARGUMENTS
