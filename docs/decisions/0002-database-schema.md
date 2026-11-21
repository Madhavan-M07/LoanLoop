# 0002. Database schema for loan files (PostgreSQL)
Date: 2026-11-21 · Status: Accepted

(0001 is reserved for the stack & LLM/deterministic-boundary ADR on the roadmap.)

## Context
All loan data lives in an in-memory `Store` and is lost on restart. Nothing can go to a real
processor until it persists. This is infrastructure for every outcome (O1–O6): O2 (days to
"file complete") and O6 (% fields corrected) cannot even be measured without durable history.

Constraints:
- **Multi-tenant:** many brokerages share one database. A processor sees only their
  organization's loans; a borrower only their own loan.
- **Audit:** every state change records who/what, when, and before → after
  (`.claude/rules/data-security.md`).
- **Changing extraction schemas:** new document types (1099, tax return, ...) arrive often.
- **Concurrency:** borrowers upload several photos at once; we already saw duplicate drafts.
- Free tier: one small Postgres 16 on the VPS. Synthetic data only for now.

## Options considered
1. **Fully relational:** a table per document type with a column per extracted field.
   Strong typing in SQL, but every new document type or field means a migration, and the
   evidence and classification data are nested lists.
2. **Everything as JSONB documents:** one JSON blob per loan. Fast to build, but no
   foreign keys, no per-row locking and no constraints, and tenant filtering is weak.
3. **Hybrid (chosen):** relational columns for everything we filter, join, lock or
   constrain (ids, org, loan, status, timestamps, money), plus JSONB for the nested,
   LLM-produced payloads (classification, extracted fields, evidence). Pydantic models
   validate the JSONB on the way in and out.

## Decision
Hybrid schema. Seven tables:

| Table | Key columns | Notes |
|---|---|---|
| `organizations` | `id`, `name`, `policy` JSONB | Lender policy validated by `LenderPolicy` |
| `loans` | `id`, `org_id` → organizations, `stage`, `monthly_debts` NUMERIC(14,2), `required_docs` TEXT[], `last_activity_at` | Index `(org_id, stage)`, `(org_id, last_activity_at)` for queue and "stuck" views |
| `documents` | `id`, `loan_id` → loans, `status`, `doc_type`, `classification` JSONB, `fields` JSONB, `review_reasons` JSONB, `uploaded_by`, `uploaded_at` | Index `(loan_id, doc_type)` |
| `rule_results` | `id`, `loan_id`, `code`, `severity`, `message`, `document_id` → documents (nullable), `borrower_action`, `data` JSONB, `evaluated_at` | Derived data: replaced in one transaction on each evaluation |
| `message_drafts` | `id`, `loan_id`, `body`, `status`, `request_key`, `created_by/at`, `decided_by/at` | **Partial unique index** on `(loan_id, request_key)` while status is pending/send_failed, so the database itself blocks duplicate drafts |
| `audit_events` | `id` BIGSERIAL, `at`, `actor`, `action`, `org_id`, `loan_id`, `detail`, `before` JSONB, `after` JSONB | **Append-only:** a trigger rejects UPDATE and DELETE |
| `outbox_messages` | `id`, `loan_id`, `channel`, `body`, `created_at`, `sent_at` | Written in the same transaction as the approval (transactional outbox) |

Conventions:
- **IDs:** text primary keys, app-generated as `<prefix>-<uuid4>` (e.g. `doc-3f2a…`).
  Today's counter only works in one process. Demo ids keep their current values.
- **Enums** (stage, status, doc_type, severity) are TEXT + CHECK constraints, not Postgres
  ENUM types, because adding a value to a PG enum is awkward in migrations.
- **Money** is NUMERIC(14,2); ratios are NUMERIC(5,3). Never float.
- **Time** is TIMESTAMPTZ, always UTC.
- **Tenancy** is enforced in the service layer (as today) and every loan query filters by
  `org_id`. Postgres row-level security is deferred until there is more than one service
  writing to the database.
- **Locking:** `Store.loan_lock()` becomes `SELECT … FROM loans WHERE id = … FOR UPDATE`
  inside the transaction.
- **Principals** (tokens and identities) stay in config for now; a users table comes with auth.
- **Raw document text and files** are not stored in this step. Files go to object storage
  later; only extracted fields are stored here.
- Schema changes go through **Alembic** only; an applied migration is never edited.

## Consequences
- Adding a document type is a Pydantic model change, not a migration. Querying inside
  extracted fields (e.g. "all paystubs from employer X") needs JSONB operators or a later
  generated column.
- Duplicate drafts and audit tampering are now blocked by the database itself, not only by
  application code.
- `AuditEvent` gains optional `before` / `after` fields (domain model change), so audit rows
  can show before → after as the data-security rule requires.
- Extracted fields contain synthetic PII today. **Before any real borrower data:** encrypt
  sensitive JSONB at rest (pgcrypto or app-level), plus backups. This is tracked for Phase 5.
- Revisit row-level security when the MCP server or Temporal workers write to the database
  directly.
