# LoanLoop Roadmap

Outcome-first: each phase names the outcomes it serves (see CLAUDE.md §1). Check items off as they're verified, not just written.

## Phase 0: Foundations
- [x] Claude Code project setup (CLAUDE.md, rules, skills, subagents, hooks, MCP, settings)
- [x] CI on every push to `main`: secret scan (project scanner + gitleaks), ruff lint + format, mypy, tests
- [ ] Working-backwards product doc `docs/PRODUCT.md` (customer, problem, outcomes, org value)
- [ ] Talk to 3–5 loan processors/brokers; record findings in `docs/customer-discovery.md`
- [ ] Architecture doc `docs/ARCHITECTURE.md` + ADR 0001 (stack & LLM/deterministic boundary)

## Phase 1: Document intelligence (O1, O6)
- [ ] Synthetic borrower document generator (paystub, W-2, bank statement) + ground truth
- [ ] FastAPI skeleton, Postgres schema, Alembic, document upload
- [ ] Classify agent + extract agent (structured output, evidence, validation)
- [ ] Eval runner with field-level accuracy, wired into CI

## Phase 2: Rules engine (O3)
- [ ] Income calculation, DTI, document age, cross-document consistency (pure Python, 100% tested)
- [ ] Conditions list generated from rule results

## Phase 3: Workflow & human approval (O2, O4)
- [ ] Temporal LoanFileWorkflow: intake → extract → check → conditions → approval signal → send
- [ ] Reminder/escalation timers; crash-and-resume test
- [ ] Next.js processor dashboard: file queue, evidence view, approve/reject

## Phase 4: Agents over MCP (O4, O5)
- [ ] LoanLoop MCP server with borrower/processor scopes + scope-denial tests
- [ ] OpenClaw borrower channel (status, missing docs, photo upload)
- [ ] Hermes processor ops agent (stuck files, daily summary)
- [ ] Prompt-injection adversarial documents in evals

## Phase 5: Production (all)
- [ ] Docker Compose + Coolify on Oracle Always Free VPS, HTTPS
- [ ] Langfuse tracing, structured logs with PII masking, backups, RUNBOOK
- [ ] Outcome metrics dashboard (minutes saved, days saved, accuracy)
- [ ] `/ship-check` passes

## Phase 6: Proof
- [ ] README with live demo link, architecture diagram, metrics
- [ ] 3-minute demo video
- [ ] Application write-up from BUILD_LOG (what agents did / what I fixed / what broke)
