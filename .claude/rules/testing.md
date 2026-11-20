---
paths:
  - "**/tests/**"
  - "**/*.test.ts"
  - "**/*.test.tsx"
  - "evals/**"
---

# Testing

- **Pyramid:** many fast unit tests (rules engine = 100% branch coverage), fewer integration tests (API + real Postgres via Docker or testcontainers), a few end-to-end tests (upload → workflow → approval).
- **Never call a real LLM in unit or integration tests.** Use the fake client in `app/llm/fake.py` with recorded fixtures. Real LLM calls happen only in `evals/`.
- **Test failure paths explicitly:** LLM timeout, malformed LLM JSON, wrong document type, expired document, borrower never responds, duplicate upload, wrong-scope MCP access, prompt-injection document.
- Test names describe behavior: `test_paystub_older_than_30_days_creates_condition`.
- A bug fix starts with a failing test that reproduces it.
- Don't weaken or delete a failing test to make it pass. Fix the code, or explain why the test is wrong.
- **Evals ≠ tests:** evals measure LLM quality on synthetic documents with ground truth (field-level accuracy, per document type). Record results in the PR/BUILD_LOG.
