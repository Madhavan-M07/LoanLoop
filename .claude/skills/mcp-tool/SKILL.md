---
name: mcp-tool
description: Add or change a tool on the LoanLoop MCP server (used by OpenClaw and Hermes) with correct scope, schemas, audit logging and tests. Use whenever an agent needs a new capability.
---

# Add an MCP tool

Tool request: $ARGUMENTS

1. **Justify it.** Which agent needs it (OpenClaw = borrower, Hermes = processor), and which outcome does it serve? Can an existing tool do the job?
2. **Design the contract first:**
   - name (`verb_noun`), scope (`borrower` | `processor`), read-only or draft-only
   - Pydantic input/output; return the minimum data, with PII masked
   - a description written for the agent: what it does, when to use it, what not to use it for
3. **Implement** as a thin call to the backend API. No business logic in `mcp/`. Scope comes from the auth token, never from arguments.
4. **Tests (required):** happy path; **wrong-scope denial** (borrower A → loan B); invalid input; backend timeout/down; audit row written.
5. Run the `security-auditor` agent on the diff.
6. Update the tool list in `mcp/README.md` and note it in `/build-log`.
