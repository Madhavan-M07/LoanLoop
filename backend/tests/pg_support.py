"""Test-only Postgres support: throwaway databases and a read-only view for assertions.

Speed: the schema is migrated and the demo data seeded ONCE into a template database; each
test gets `CREATE DATABASE ... TEMPLATE` (a file copy, milliseconds) and drops it afterwards.
"""

from __future__ import annotations

import asyncio
import threading
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime
from pathlib import Path
from typing import Any, TypeVar

import asyncpg
from alembic import command
from alembic.config import Config
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.data.postgres import PostgresRepository, PostgresSession, _draft, _loan
from app.data.seed import load_demo
from app.data.tables import audit_events, loans, message_drafts, outbox_messages
from app.domain.models import AuditEvent, Document, Loan, MessageDraft, RuleResult

BACKEND = Path(__file__).resolve().parents[1]
T = TypeVar("T")


def dsn(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


def with_db(url: str, name: str) -> str:
    return url.rsplit("/", 1)[0] + "/" + name


async def admin(url: str, sql: str) -> None:
    conn = await asyncpg.connect(dsn(url))
    try:
        await conn.execute(sql)
    finally:
        await conn.close()


def engine_for(url: str):
    # NullPool: every session opens its own connection in the CURRENT event loop. Tests run code
    # in several loops (pytest's, TestClient's, snapshot threads); pooled connections can't move
    # between loops.
    return create_async_engine(url, poolclass=NullPool)


def make_template(server_url: str, demo: dict[str, Any], now: datetime) -> str:
    name = f"loanloop_tmpl_{uuid.uuid4().hex[:10]}"
    asyncio.run(admin(server_url, f'CREATE DATABASE "{name}"'))
    url = with_db(server_url, name)
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.attributes["database_url"] = url
    cfg.attributes["configure_logging"] = False
    command.upgrade(cfg, "head")
    asyncio.run(load_demo(PostgresRepository(engine_for(url), lambda: now), demo))
    return name


def clone(server_url: str, template: str) -> str:
    name = f"loanloop_test_{uuid.uuid4().hex[:12]}"
    asyncio.run(admin(server_url, f'CREATE DATABASE "{name}" TEMPLATE "{template}"'))
    return name


def drop(server_url: str, name: str) -> None:
    asyncio.run(admin(server_url, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))


def _in_thread(fn: Callable[[], Awaitable[T]]) -> T:
    """Run a coroutine to completion on a private loop in another thread. Lets synchronous test
    assertions (`store.loans[...]`) read the database even from inside a running event loop."""
    box: dict[str, Any] = {}

    def run() -> None:
        try:
            box["value"] = asyncio.run(fn())
        except BaseException as e:  # re-raised in the caller's thread
            box["error"] = e

    t = threading.Thread(target=run)
    t.start()
    t.join()
    if "error" in box:
        raise box["error"]
    return box["value"]


class PgTestStore(PostgresRepository):
    """The real Postgres repository, plus read-only snapshots with the same shape as the
    in-memory Store's attributes, so the same assertions run against both backends."""

    def __init__(self, url: str, clock: Callable[[], datetime]) -> None:
        super().__init__(engine_for(url), clock)
        self.url = url

    def _snapshot(self, fn: Callable[[PostgresSession], Awaitable[T]]) -> T:
        async def go() -> T:
            repo = PostgresRepository(engine_for(self.url), self.now)
            async with repo.session() as s:
                return await fn(s)

        return _in_thread(go)

    @property
    def loans(self) -> dict[str, Loan]:
        async def q(s: PostgresSession) -> dict[str, Loan]:
            rows = (await s.conn.execute(select(loans).order_by(loans.c.id))).mappings().all()
            return {r["id"]: _loan(r) for r in rows}

        return self._snapshot(q)

    @property
    def documents(self) -> dict[str, list[Document]]:
        async def q(s: PostgresSession) -> dict[str, list[Document]]:
            ids = (await s.conn.execute(select(loans.c.id))).scalars().all()
            return {i: await s.documents(i) for i in ids}

        return self._snapshot(q)

    @property
    def results(self) -> dict[str, list[RuleResult]]:
        async def q(s: PostgresSession) -> dict[str, list[RuleResult]]:
            ids = (await s.conn.execute(select(loans.c.id))).scalars().all()
            return {i: await s.results(i) for i in ids}

        return self._snapshot(q)

    @property
    def drafts(self) -> dict[str, MessageDraft]:
        async def q(s: PostgresSession) -> dict[str, MessageDraft]:
            stmt = select(message_drafts).order_by(message_drafts.c.created_at, message_drafts.c.id)
            return {r["id"]: _draft(r) for r in (await s.conn.execute(stmt)).mappings().all()}

        return self._snapshot(q)

    @property
    def audit_log(self) -> list[AuditEvent]:
        async def q(s: PostgresSession) -> list[AuditEvent]:
            stmt = select(audit_events).order_by(audit_events.c.id)
            return [
                AuditEvent(
                    at=r["at"],
                    actor=r["actor"],
                    action=r["action"],
                    loan_id=r["loan_id"],
                    org_id=r["org_id"],
                    detail=r["detail"],
                )
                for r in (await s.conn.execute(stmt)).mappings().all()
            ]

        return self._snapshot(q)

    @property
    def outbox(self) -> list[dict[str, str]]:
        async def q(s: PostgresSession) -> list[dict[str, str]]:
            stmt = select(outbox_messages).order_by(outbox_messages.c.created_at)
            return [
                {"loan_id": r["loan_id"], "channel": r["channel"], "body": r["body"]}
                for r in (await s.conn.execute(stmt)).mappings().all()
            ]

        return self._snapshot(q)
