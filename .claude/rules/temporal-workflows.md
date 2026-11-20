---
paths:
  - "backend/app/workflows/**"
---

# Temporal workflows

- **Workflow code must be deterministic:** no I/O, no LLM calls, no `datetime.now()`, no `random`, no network. Use `workflow.now()` and `workflow.sleep()`. All side effects go in **activities**.
- One workflow per loan file (`LoanFileWorkflow`, id = `loan-{loan_id}`). State changes come from activities' results and **signals** (e.g. `processor_approved`, `document_uploaded`).
- Human approval = wait on a signal with a timeout. On timeout, escalate (notify the processor). Never auto-approve.
- Every activity: explicit `start_to_close_timeout`, a retry policy, and **idempotency** (safe to run twice; use idempotency keys for sends and uploads).
- Non-retryable errors (validation failures, bad documents) raise `ApplicationError(non_retryable=True)` and route the file to `needs_human_review`.
- Changing a running workflow's logic requires `workflow.patched()` / versioning. Note it in an ADR.
- Test with the Temporal test environment (time-skipping), covering the happy path, timeout/escalation, and crash-and-resume.
