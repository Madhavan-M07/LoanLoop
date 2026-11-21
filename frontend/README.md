# LoanLoop frontend

Processor dashboard and borrower upload simulator. Next.js (App Router, server components) +
Tailwind. Talks to the FastAPI backend from the server only; the browser never holds the API
token (it lives in an httpOnly cookie).

## Run it

```bash
# 1. Database + backend (see the repo CLAUDE.md), API on http://127.0.0.1:8000
# 2. Frontend
cp .env.example .env.local   # optional: change LOANLOOP_API_URL
npm install
npm run dev                  # http://localhost:3000
```

Sign in with one of the demo users (development only):

| User | Shows |
|---|---|
| Anita (Acme processor) | Loan queue, loan file with evidence, approval inbox |
| Ravi (Beta processor) | Only Beta's files: tenant isolation |
| Priya / John (borrowers) | Upload simulator and their own loan status |
| Hermes (AI agent) | Can read and draft; the API refuses its approvals |

## Screens

- **Loan queue** `/loans`: every file with stage, idle days, open issues, messages to approve; "stuck" filter.
- **Loan file** `/loans/[id]`: required documents, rule checks, extracted fields with the source snippet behind each value, approval, activity timeline with before → after.
- **Approval inbox** `/inbox`: approve & send, or reject. Nothing reaches a borrower without this.
- **Borrower simulator** `/upload`: build a synthetic paystub / W-2 / bank statement (or a prompt-injection test document), edit it, upload it.

## Checks

```bash
npm run lint && npm run typecheck && npm test && npm run build
```

## API types

Generated, never hand-written. After changing the backend API:

```bash
cd ../backend && uv run python scripts/export_openapi.py
cd ../frontend && npm run gen:api
```

CI fails if `openapi.json` or `src/lib/api/schema.d.ts` is out of date.
