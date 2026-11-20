---
paths:
  - "frontend/**"
---

# Frontend (Next.js processor dashboard)

- Next.js App Router, TypeScript `strict`, no `any`. Server components by default; `"use client"` only for interactivity.
- Data comes from the FastAPI backend via a typed client generated from its OpenAPI schema (`frontend/lib/api/`). No hand-written fetch shapes.
- The dashboard exists to move outcomes: each screen should make a processor faster (O1, O5) or show proof (outcome metrics page). Don't add screens without a named outcome.
- Every AI-produced value is displayed with its **source evidence** and a **confidence/needs-review** state. Approve and reject actions are explicit and audited.
- States to handle on every data view: loading, empty, error, stale.
- Tailwind for styling; accessible (labels, keyboard, contrast). Works at laptop width first.
- Tests: Vitest + Testing Library for components; Playwright (via MCP) for the main approval flow.
