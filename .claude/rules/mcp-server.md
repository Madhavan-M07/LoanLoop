---
paths:
  - "mcp/**"
---

# LoanLoop MCP server

The MCP server is the **only** way OpenClaw and Hermes touch LoanLoop. It is a thin, scoped layer over the backend API. No business logic lives here.

Every tool:
- Declares a scope: `borrower` (own loan only) or `processor` (own brokerage). The scope comes from the authenticated token, **never from tool arguments**.
- Has typed input and output (Pydantic). Its description says what it does, when to use it, and what it must not be used for, because the agent reads it.
- Is **read-only by default**. Write tools (e.g. `draft_borrower_message`) only create *drafts or requests*. Final actions (send, approve) need a human signal in the workflow.
- Returns minimal data: no SSNs or full account numbers, only what the agent needs.
- Is rate-limited and audit-logged (tool, caller, loan_id, result status).
- Has tests: happy path, wrong-scope denial (borrower A asking for loan B), invalid input, and backend-down behavior.

Clients: **OpenClaw** = borrower channel (borrower scope). **Hermes** = processor ops (processor scope).
