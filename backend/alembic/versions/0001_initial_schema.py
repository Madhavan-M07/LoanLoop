"""initial schema: loan files, documents, rule results, drafts, audit log, outbox

Design: docs/decisions/0002-database-schema.md.

Revision ID: 0001
Revises:
Create Date: 2026-11-21

Never edit a migration that has been applied anywhere. Write a new one.
Values are written out literally (not imported from the app) so this file stays a frozen
snapshot of the schema at this revision, whatever the code looks like later.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TS = sa.DateTime(timezone=True)


def _ts(name: str, *, nullable: bool = False) -> sa.Column:
    return sa.Column(name, TS, nullable=nullable)


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("id", sa.Text, nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("policy", JSONB, nullable=False),
        sa.Column("created_at", TS, nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id", name="pk_organizations"),
    )

    op.create_table(
        "loans",
        sa.Column("id", sa.Text, nullable=False),
        sa.Column("org_id", sa.Text, nullable=False),
        sa.Column("borrower_name", sa.Text, nullable=False),
        sa.Column("borrower_subject", sa.Text, nullable=False),
        sa.Column("loan_officer", sa.Text, nullable=False),
        sa.Column("monthly_debts", sa.Numeric(14, 2), nullable=False),
        sa.Column("required_docs", ARRAY(sa.Text), nullable=False),
        sa.Column("stage", sa.Text, nullable=False),
        _ts("created_at"),
        _ts("last_activity_at"),
        sa.Column("telegram_chat_id", sa.Text),
        sa.PrimaryKeyConstraint("id", name="pk_loans"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], name="fk_loans_org_id"),
        sa.CheckConstraint(
            "stage IN ('collecting_documents', 'needs_processor_review', 'file_complete')",
            name=op.f("ck_loans_stage"),
        ),
        sa.CheckConstraint("monthly_debts >= 0", name=op.f("ck_loans_monthly_debts_non_negative")),
    )
    op.create_index("ix_loans_org_id_stage", "loans", ["org_id", "stage"])
    op.create_index("ix_loans_org_id_last_activity_at", "loans", ["org_id", "last_activity_at"])

    op.create_table(
        "documents",
        sa.Column("id", sa.Text, nullable=False),
        sa.Column("loan_id", sa.Text, nullable=False),
        sa.Column("filename", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("doc_type", sa.Text, nullable=False),
        sa.Column("classification", JSONB),
        sa.Column("fields", JSONB),
        sa.Column("review_reasons", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("uploaded_by", sa.Text, nullable=False),
        _ts("uploaded_at"),
        sa.PrimaryKeyConstraint("id", name="pk_documents"),
        sa.ForeignKeyConstraint(["loan_id"], ["loans.id"], name="fk_documents_loan_id"),
        sa.CheckConstraint(
            "status IN ('received', 'extracted', 'needs_review', 'rejected')",
            name=op.f("ck_documents_status"),
        ),
        sa.CheckConstraint(
            "doc_type IN ('paystub', 'w2', 'bank_statement', 'unknown')",
            name=op.f("ck_documents_doc_type"),
        ),
    )
    op.create_index("ix_documents_loan_id_doc_type", "documents", ["loan_id", "doc_type"])

    op.create_table(
        "rule_results",
        sa.Column("id", sa.BigInteger, sa.Identity(always=True), nullable=False),
        sa.Column("loan_id", sa.Text, nullable=False),
        sa.Column("code", sa.Text, nullable=False),
        sa.Column("severity", sa.Text, nullable=False),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("document_id", sa.Text),
        sa.Column("borrower_action", sa.Text),
        sa.Column("data", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        _ts("evaluated_at"),
        sa.PrimaryKeyConstraint("id", name="pk_rule_results"),
        sa.ForeignKeyConstraint(["loan_id"], ["loans.id"], name="fk_rule_results_loan_id"),
        sa.ForeignKeyConstraint(
            ["document_id"], ["documents.id"], name="fk_rule_results_document_id"
        ),
        sa.CheckConstraint(
            "severity IN ('pass', 'warn', 'fail')", name=op.f("ck_rule_results_severity")
        ),
    )
    op.create_index("ix_rule_results_loan_id", "rule_results", ["loan_id"])

    op.create_table(
        "message_drafts",
        sa.Column("id", sa.Text, nullable=False),
        sa.Column("loan_id", sa.Text, nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("created_by", sa.Text, nullable=False),
        _ts("created_at"),
        sa.Column("request_key", sa.Text),
        sa.Column("decided_by", sa.Text),
        _ts("decided_at", nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_message_drafts"),
        sa.ForeignKeyConstraint(["loan_id"], ["loans.id"], name="fk_message_drafts_loan_id"),
        sa.CheckConstraint(
            "status IN ('pending_approval', 'approved', 'rejected', 'sent', 'send_failed')",
            name=op.f("ck_message_drafts_status"),
        ),
        sa.CheckConstraint(
            "char_length(body) BETWEEN 1 AND 1500", name=op.f("ck_message_drafts_body_length")
        ),
    )
    op.create_index("ix_message_drafts_loan_id_status", "message_drafts", ["loan_id", "status"])
    op.create_index(
        "uq_message_drafts_open_request",
        "message_drafts",
        ["loan_id", "request_key"],
        unique=True,
        postgresql_where=sa.text(
            "request_key IS NOT NULL AND status IN ('pending_approval', 'send_failed')"
        ),
    )

    op.create_table(
        "audit_events",
        sa.Column("id", sa.BigInteger, sa.Identity(always=True), nullable=False),
        sa.Column("at", TS, nullable=False, server_default=sa.func.now()),
        sa.Column("actor", sa.Text, nullable=False),
        sa.Column("action", sa.Text, nullable=False),
        sa.Column("org_id", sa.Text),
        sa.Column("loan_id", sa.Text),
        sa.Column("detail", sa.Text, nullable=False, server_default=""),
        sa.Column("before", JSONB),
        sa.Column("after", JSONB),
        sa.PrimaryKeyConstraint("id", name="pk_audit_events"),
    )
    op.create_index("ix_audit_events_loan_id_at", "audit_events", ["loan_id", "at"])
    op.create_index("ix_audit_events_org_id_at", "audit_events", ["org_id", "at"])
    # Append-only: history can be added to, never rewritten or erased.
    op.execute(
        """
        CREATE FUNCTION audit_events_append_only() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'audit_events is append-only (% is not allowed)', TG_OP
                USING ERRCODE = 'insufficient_privilege';
        END;
        $$;
        """
    )
    op.execute(
        "CREATE TRIGGER audit_events_no_update_delete BEFORE UPDATE OR DELETE ON audit_events "
        "FOR EACH ROW EXECUTE FUNCTION audit_events_append_only();"
    )
    op.execute(
        "CREATE TRIGGER audit_events_no_truncate BEFORE TRUNCATE ON audit_events "
        "FOR EACH STATEMENT EXECUTE FUNCTION audit_events_append_only();"
    )

    op.create_table(
        "outbox_messages",
        sa.Column("id", sa.Text, nullable=False),
        sa.Column("loan_id", sa.Text, nullable=False),
        sa.Column("draft_id", sa.Text),
        sa.Column("channel", sa.Text, nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        _ts("created_at"),
        _ts("sent_at", nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_outbox_messages"),
        sa.ForeignKeyConstraint(["loan_id"], ["loans.id"], name="fk_outbox_messages_loan_id"),
        sa.ForeignKeyConstraint(
            ["draft_id"], ["message_drafts.id"], name="fk_outbox_messages_draft_id"
        ),
    )
    op.create_index("ix_outbox_messages_loan_id", "outbox_messages", ["loan_id"])


def downgrade() -> None:
    op.drop_table("outbox_messages")
    op.execute("DROP TRIGGER audit_events_no_truncate ON audit_events;")
    op.execute("DROP TRIGGER audit_events_no_update_delete ON audit_events;")
    op.drop_table("audit_events")
    op.execute("DROP FUNCTION audit_events_append_only();")
    op.drop_table("message_drafts")
    op.drop_table("rule_results")
    op.drop_table("documents")
    op.drop_table("loans")
    op.drop_table("organizations")
