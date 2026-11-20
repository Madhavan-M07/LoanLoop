---
paths:
  - "backend/**/*.py"
  - "mcp/**/*.py"
  - "evals/**/*.py"
---

# Python conventions

- Python 3.12, fully type-hinted, `ruff` for format and lint. Pydantic v2 models at every boundary (API, LLM output, MCP tool I/O).
- Layout: `api/` (thin routes) → `services/` (use-cases) → `db/` (SQLAlchemy 2 repositories). Routes never touch the ORM directly.
- Money is `Decimal`, never float. Percentages (DTI, LTV) are `Decimal` with explicit rounding (`ROUND_HALF_UP`, 2 or 3 places as documented).
- Dates are timezone-aware UTC (`datetime.now(UTC)`).
- Errors: raise domain exceptions (`app/core/errors.py`), map them to HTTP in one exception handler. Never return a bare 500 with a stack trace.
- External calls (LLM, messaging, storage) go through an interface in `app/llm/` or `app/integrations/`, so tests can fake them. Always set a timeout. Retry only idempotent calls.
- DB changes go through a new Alembic migration only. Never edit an applied migration.
- Config: `app/core/config.py` (pydantic-settings). No `os.getenv` scattered around.
- Logging: structured (JSON), with `loan_id` and `request_id` in context, PII masked.
