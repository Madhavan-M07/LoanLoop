"""Alembic migrations against a real Postgres (throwaway databases, dropped afterwards).

Proves: the schema applies to an empty database and rolls back cleanly; the code's table
definitions match what the migrations build; and the database itself enforces the guarantees
from ADR 0002 (no duplicate open drafts, append-only audit log, only valid enum values).

Runs only when LOANLOOP_TEST_DATABASE_URL is set (local Docker Postgres, or CI's service).
"""

import asyncio
import os
import re
import uuid
from collections.abc import Iterator
from enum import StrEnum
from pathlib import Path

import asyncpg
import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy.ext.asyncio import create_async_engine

from app.data.tables import metadata
from app.domain.models import (
    OPEN_DRAFT_STATUSES,
    DocStatus,
    DocType,
    DraftStatus,
    LoanStage,
    Severity,
)

REAL_DB = os.environ.get("LOANLOOP_TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(
    not REAL_DB, reason="set LOANLOOP_TEST_DATABASE_URL to run against Postgres"
)

BACKEND = Path(__file__).resolve().parents[1]
TABLES = {
    "organizations",
    "loans",
    "documents",
    "rule_results",
    "message_drafts",
    "audit_events",
    "outbox_messages",
}


def _dsn(url: str) -> str:
    """asyncpg wants a plain postgresql:// DSN, not SQLAlchemy's +asyncpg form."""
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


def _with_db(url: str, name: str) -> str:
    return url.rsplit("/", 1)[0] + "/" + name


async def _admin(sql: str) -> None:
    conn = await asyncpg.connect(_dsn(REAL_DB))
    try:
        await conn.execute(sql)
    finally:
        await conn.close()


def _alembic(url: str) -> Config:
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.attributes["database_url"] = url
    cfg.attributes["configure_logging"] = False  # keep pytest's log capture intact
    return cfg


@pytest.fixture
def empty_db() -> Iterator[str]:
    name = f"loanloop_test_{uuid.uuid4().hex[:12]}"
    asyncio.run(_admin(f'CREATE DATABASE "{name}"'))
    try:
        yield _with_db(REAL_DB, name)
    finally:
        asyncio.run(_admin(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))


@pytest.fixture
def migrated_db(empty_db: str) -> str:
    command.upgrade(_alembic(empty_db), "head")
    return empty_db


def _query(url: str, sql: str, *args: object) -> list[asyncpg.Record]:
    async def go() -> list[asyncpg.Record]:
        conn = await asyncpg.connect(_dsn(url))
        try:
            return await conn.fetch(sql, *args)
        finally:
            await conn.close()

    return asyncio.run(go())


def _execute(url: str, *statements: str) -> None:
    async def go() -> None:
        conn = await asyncpg.connect(_dsn(url))
        try:
            for s in statements:
                await conn.execute(s)
        finally:
            await conn.close()

    asyncio.run(go())


def _tables(url: str) -> set[str]:
    rows = _query(url, "SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
    return {r["tablename"] for r in rows}


SEED = [
    """INSERT INTO organizations (id, name, policy)
       VALUES ('org-1', 'Acme Mortgage', '{"paystub_max_age_days": 30}')""",
    """INSERT INTO loans (id, org_id, borrower_name, borrower_subject, loan_officer,
                          monthly_debts, required_docs, stage, created_at, last_activity_at)
       VALUES ('loan-1', 'org-1', 'Test Borrower', 'b-1', 'lo-1', 450.00,
               ARRAY['paystub', 'w2'], 'collecting_documents', now(), now())""",
]


def _draft(draft_id: str, status: str, request_key: str = "paystub") -> str:
    return f"""INSERT INTO message_drafts (id, loan_id, body, status, created_by, created_at,
                                         request_key)
               VALUES ('{draft_id}', 'loan-1', 'Please upload your latest paystub.',
                       '{status}', 'conditions_agent', now(), '{request_key}')"""  # noqa: S608 - test-only literals


# ---- schema lifecycle ---------------------------------------------------------------------


def test_upgrade_creates_all_tables_on_an_empty_database(migrated_db):
    assert _tables(migrated_db) == TABLES | {"alembic_version"}
    assert _query(migrated_db, "SELECT version_num FROM alembic_version")[0][0] == "0001"


def test_downgrade_removes_everything_and_upgrade_works_again(migrated_db):
    cfg = _alembic(migrated_db)
    command.downgrade(cfg, "base")
    assert _tables(migrated_db) == {"alembic_version"}
    functions = _query(
        migrated_db, "SELECT 1 FROM pg_proc WHERE proname = 'audit_events_append_only'"
    )
    assert functions == []  # trigger function removed too, nothing left behind
    command.upgrade(cfg, "head")
    assert _tables(migrated_db) == TABLES | {"alembic_version"}


def test_table_definitions_in_code_match_the_migrated_database(migrated_db):
    """If someone edits app/data/tables.py without a migration (or vice versa), this fails."""

    async def diff() -> list:
        engine = create_async_engine(migrated_db)
        try:
            async with engine.connect() as conn:
                return await conn.run_sync(
                    lambda c: compare_metadata(MigrationContext.configure(c), metadata)
                )
        finally:
            await engine.dispose()

    assert asyncio.run(diff()) == []


# ---- guarantees the database enforces itself ----------------------------------------------


def test_database_rejects_a_second_open_draft_for_the_same_request(migrated_db):
    _execute(migrated_db, *SEED, _draft("d-1", "pending_approval"))
    with pytest.raises(asyncpg.UniqueViolationError):
        _execute(migrated_db, _draft("d-2", "pending_approval"))
    with pytest.raises(asyncpg.UniqueViolationError):
        _execute(migrated_db, _draft("d-3", "send_failed"))  # still open, still a duplicate


def test_new_draft_is_allowed_once_the_previous_one_is_closed(migrated_db):
    _execute(
        migrated_db,
        *SEED,
        _draft("d-1", "pending_approval"),
        "UPDATE message_drafts SET status = 'sent' WHERE id = 'd-1'",
        _draft("d-2", "pending_approval"),  # same request, but the first is no longer open
    )
    assert len(_query(migrated_db, "SELECT id FROM message_drafts")) == 2


def test_audit_log_accepts_inserts_but_rejects_update_delete_and_truncate(migrated_db):
    _execute(
        migrated_db,
        """INSERT INTO audit_events (actor, action, loan_id, detail, before, after)
           VALUES ('proc-1', 'stage_changed', 'loan-1', '',
                   '{"stage": "collecting_documents"}', '{"stage": "file_complete"}')""",
    )
    for tamper in (
        "UPDATE audit_events SET actor = 'someone-else'",
        "DELETE FROM audit_events",
        "TRUNCATE audit_events",
    ):
        with pytest.raises(asyncpg.InsufficientPrivilegeError, match="append-only"):
            _execute(migrated_db, tamper)
    assert len(_query(migrated_db, "SELECT id FROM audit_events")) == 1


def test_invalid_stage_is_rejected(migrated_db):
    bad_loan = SEED[1].replace("'collecting_documents'", "'approved_by_ai'")
    with pytest.raises(asyncpg.CheckViolationError):
        _execute(migrated_db, SEED[0], bad_loan)


def test_negative_monthly_debts_are_rejected(migrated_db):
    with pytest.raises(asyncpg.CheckViolationError):
        _execute(migrated_db, SEED[0], SEED[1].replace("450.00", "-1.00"))


@pytest.mark.parametrize(
    ("constraint", "enum"),
    [
        ("ck_loans_stage", LoanStage),
        ("ck_documents_status", DocStatus),
        ("ck_documents_doc_type", DocType),
        ("ck_rule_results_severity", Severity),
        ("ck_message_drafts_status", DraftStatus),
    ],
)
def test_database_allowed_values_match_domain_enums(migrated_db, constraint, enum: type[StrEnum]):
    """A new enum value in the domain needs a migration; this catches a forgotten one."""
    row = _query(
        migrated_db,
        "SELECT pg_get_constraintdef(oid) AS d FROM pg_constraint WHERE conname = $1",
        constraint,
    )
    allowed = set(re.findall(r"'([^']+)'::text", row[0]["d"]))
    assert allowed == {e.value for e in enum}


def test_duplicate_draft_rule_covers_exactly_the_open_draft_statuses(migrated_db):
    """The unique index must use the domain's OPEN_DRAFT_STATUSES, or real drafts slip past it."""
    row = _query(
        migrated_db,
        "SELECT pg_get_indexdef(indexrelid) AS d FROM pg_index "
        "WHERE indexrelid = 'uq_message_drafts_open_request'::regclass",
    )
    covered = set(re.findall(r"'([^']+)'::text", row[0]["d"]))
    assert covered == {s.value for s in OPEN_DRAFT_STATUSES}
