"""PostgreSQL table definitions (SQLAlchemy Core). Design: docs/decisions/0002-database-schema.md.

Hybrid schema: real columns for what we filter, join, lock or constrain; JSONB for nested,
LLM-produced payloads (validated by the Pydantic domain models on the way in and out).

These definitions describe the CURRENT schema. The database is only ever changed by Alembic
migrations (backend/alembic/versions/); tests/test_migrations.py fails if the two disagree.
"""

from __future__ import annotations

from enum import StrEnum

from sqlalchemy import (
    ARRAY,
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    MetaData,
    Numeric,
    Table,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB

from app.domain.models import (
    OPEN_DRAFT_STATUSES,
    DocStatus,
    DocType,
    DraftStatus,
    LoanStage,
    Severity,
)

# Stable constraint names, so migrations can refer to them.
metadata = MetaData(
    naming_convention={
        "pk": "pk_%(table_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s",
        "ix": "ix_%(table_name)s_%(column_0_N_name)s",
        "uq": "uq_%(table_name)s_%(column_0_N_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
    }
)


def one_of(column: str, enum: type[StrEnum]) -> str:
    """CHECK expression allowing exactly the domain enum's values (TEXT + CHECK, not PG ENUM)."""
    values = ", ".join(f"'{v.value}'" for v in enum)
    return f"{column} IN ({values})"


def _ts(name: str, *, nullable: bool = False) -> Column:
    return Column(name, DateTime(timezone=True), nullable=nullable)


organizations = Table(
    "organizations",
    metadata,
    Column("id", Text, primary_key=True),
    Column("name", Text, nullable=False),
    Column("policy", JSONB, nullable=False),  # LenderPolicy
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

loans = Table(
    "loans",
    metadata,
    Column("id", Text, primary_key=True),
    Column("org_id", Text, ForeignKey("organizations.id"), nullable=False),
    Column("borrower_name", Text, nullable=False),
    Column("borrower_subject", Text, nullable=False),
    Column("loan_officer", Text, nullable=False),
    Column("monthly_debts", Numeric(14, 2), nullable=False),
    Column("required_docs", ARRAY(Text), nullable=False),
    Column("stage", Text, nullable=False),
    _ts("created_at"),
    _ts("last_activity_at"),
    Column("telegram_chat_id", Text),
    CheckConstraint(one_of("stage", LoanStage), name="stage"),
    CheckConstraint("monthly_debts >= 0", name="monthly_debts_non_negative"),
    Index(None, "org_id", "stage"),  # processor queue
    Index(None, "org_id", "last_activity_at"),  # "stuck files" view
)

documents = Table(
    "documents",
    metadata,
    Column("id", Text, primary_key=True),
    Column("loan_id", Text, ForeignKey("loans.id"), nullable=False),
    Column("filename", Text, nullable=False),
    Column("status", Text, nullable=False),
    Column("doc_type", Text, nullable=False),
    Column("classification", JSONB),  # Classification
    Column("fields", JSONB),  # PaystubFields | W2Fields | BankStatementFields
    Column("review_reasons", JSONB, nullable=False, server_default=text("'[]'::jsonb")),
    Column("uploaded_by", Text, nullable=False),
    _ts("uploaded_at"),
    CheckConstraint(one_of("status", DocStatus), name="status"),
    CheckConstraint(one_of("doc_type", DocType), name="doc_type"),
    Index(None, "loan_id", "doc_type"),
)

rule_results = Table(
    "rule_results",
    metadata,
    Column("id", BigInteger, Identity(always=True), primary_key=True),
    Column("loan_id", Text, ForeignKey("loans.id"), nullable=False),
    Column("code", Text, nullable=False),
    Column("severity", Text, nullable=False),
    Column("message", Text, nullable=False),
    Column("document_id", Text, ForeignKey("documents.id")),
    Column("borrower_action", Text),
    Column("data", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    _ts("evaluated_at"),
    CheckConstraint(one_of("severity", Severity), name="severity"),
    Index(None, "loan_id"),
)

_open = ", ".join(f"'{s.value}'" for s in sorted(OPEN_DRAFT_STATUSES))

message_drafts = Table(
    "message_drafts",
    metadata,
    Column("id", Text, primary_key=True),
    Column("loan_id", Text, ForeignKey("loans.id"), nullable=False),
    Column("body", Text, nullable=False),
    Column("status", Text, nullable=False),
    Column("created_by", Text, nullable=False),
    _ts("created_at"),
    Column("request_key", Text),
    Column("decided_by", Text),
    _ts("decided_at", nullable=True),
    CheckConstraint(one_of("status", DraftStatus), name="status"),
    CheckConstraint("char_length(body) BETWEEN 1 AND 1500", name="body_length"),
    Index(None, "loan_id", "status"),
    # The database itself refuses a second OPEN draft asking for the same items on one loan.
    Index(
        "uq_message_drafts_open_request",
        "loan_id",
        "request_key",
        unique=True,
        postgresql_where=text(f"request_key IS NOT NULL AND status IN ({_open})"),
    ),
)

# Append-only: a trigger (created in the migration) rejects UPDATE, DELETE and TRUNCATE.
# No foreign keys on purpose: audit history must outlive anything it refers to.
audit_events = Table(
    "audit_events",
    metadata,
    Column("id", BigInteger, Identity(always=True), primary_key=True),
    Column("at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("actor", Text, nullable=False),
    Column("action", Text, nullable=False),
    Column("org_id", Text),
    Column("loan_id", Text),
    Column("detail", Text, nullable=False, server_default=""),
    Column("before", JSONB),
    Column("after", JSONB),
    Index(None, "loan_id", "at"),
    Index(None, "org_id", "at"),
)

outbox_messages = Table(
    "outbox_messages",
    metadata,
    Column("id", Text, primary_key=True),
    Column("loan_id", Text, ForeignKey("loans.id"), nullable=False),
    Column("draft_id", Text, ForeignKey("message_drafts.id")),
    Column("channel", Text, nullable=False),
    Column("body", Text, nullable=False),
    _ts("created_at"),
    _ts("sent_at", nullable=True),
    Index(None, "loan_id"),
)
