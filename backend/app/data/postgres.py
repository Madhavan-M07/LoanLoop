"""PostgreSQL implementation of the storage interface (app/data/repository.py).

One `session()` = one database transaction (committed on success, rolled back on error).
`lock_loan` uses SELECT ... FOR NO KEY UPDATE: it serializes work on that loan, but does NOT
block inserts of child rows (documents, drafts) whose foreign-key check only needs a key-share
lock, so an upload can be recorded while the file is being re-checked.

Schema: app/data/tables.py, created by Alembic (docs/decisions/0002-database-schema.md).
"""

from __future__ import annotations

import secrets
import time
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy import RowMapping, delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine
from sqlalchemy.sql.schema import Table

from app.data.repository import Clock
from app.data.tables import (
    audit_events,
    documents,
    loans,
    message_drafts,
    organizations,
    outbox_messages,
    rule_results,
)
from app.domain.models import (
    SCHEMA_FOR,
    AuditEvent,
    Classification,
    DocType,
    Document,
    DraftStatus,
    Loan,
    LoanStage,
    MessageDraft,
    Organization,
    RuleResult,
)
from app.security.pii import mask_for_log


def time_sortable_id(prefix: str) -> str:
    """`D-0005f3a1c2b4d6e-9f3a1c2b`: microsecond timestamp, then randomness. Unique across
    processes (unlike a counter) and sorts by creation time, so listings keep upload order."""
    return f"{prefix}-{time.time_ns() // 1000:015x}-{secrets.token_hex(4)}"


class PostgresRepository:
    def __init__(self, engine: AsyncEngine, clock: Clock) -> None:
        self.engine = engine
        self.now = clock

    def new_id(self, prefix: str) -> str:
        return time_sortable_id(prefix)

    @asynccontextmanager
    async def session(self) -> AsyncIterator[PostgresSession]:
        async with self.engine.begin() as conn:  # commit on success, rollback on exception
            yield PostgresSession(conn, self.now)

    async def audit(
        self,
        actor: str,
        action: str,
        loan_id: str | None = None,
        detail: str = "",
        *,
        org_id: str | None = None,
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
    ) -> None:
        async with self.session() as s:
            await s.audit(actor, action, loan_id, detail, org_id=org_id, before=before, after=after)


async def _upsert(conn: AsyncConnection, table: Table, values: dict[str, Any]) -> None:
    stmt = insert(table).values(**values)
    await conn.execute(
        stmt.on_conflict_do_update(
            index_elements=["id"], set_={k: stmt.excluded[k] for k in values if k != "id"}
        )
    )


# ---- row <-> domain model -----------------------------------------------------------------


def _loan(r: RowMapping) -> Loan:
    return Loan(
        id=r["id"],
        org_id=r["org_id"],
        borrower_name=r["borrower_name"],
        borrower_subject=r["borrower_subject"],
        loan_officer=r["loan_officer"],
        monthly_debts=r["monthly_debts"],
        required_docs=[DocType(d) for d in r["required_docs"]],
        stage=r["stage"],
        created_at=r["created_at"],
        last_activity_at=r["last_activity_at"],
        telegram_chat_id=r["telegram_chat_id"],
    )


def _document(r: RowMapping) -> Document:
    doc_type = DocType(r["doc_type"])
    fields = r["fields"]
    return Document(
        id=r["id"],
        loan_id=r["loan_id"],
        filename=r["filename"],
        status=r["status"],
        doc_type=doc_type,
        classification=Classification.model_validate(r["classification"])
        if r["classification"] is not None
        else None,
        # Validate against the schema for THIS document type, not "whichever union member fits".
        fields=SCHEMA_FOR[doc_type].model_validate(fields) if fields is not None else None,  # type: ignore[arg-type]
        review_reasons=list(r["review_reasons"]),
        uploaded_by=r["uploaded_by"],
        uploaded_at=r["uploaded_at"],
    )


def _draft(r: RowMapping) -> MessageDraft:
    return MessageDraft.model_validate(dict(r))


class PostgresSession:
    def __init__(self, conn: AsyncConnection, clock: Clock) -> None:
        self.conn = conn
        self.now = clock

    async def _rows(self, stmt: Any) -> Sequence[RowMapping]:
        return list((await self.conn.execute(stmt)).mappings().all())

    # organizations
    async def get_org(self, org_id: str) -> Organization:
        rows = await self._rows(select(organizations).where(organizations.c.id == org_id))
        if not rows:
            raise LookupError(f"organization {org_id} is not configured")
        return Organization(id=rows[0]["id"], name=rows[0]["name"], policy=rows[0]["policy"])

    async def save_org(self, org: Organization) -> None:
        await _upsert(
            self.conn,
            organizations,
            {"id": org.id, "name": org.name, "policy": org.policy.model_dump(mode="json")},
        )

    # loans
    async def get_loan(self, loan_id: str) -> Loan | None:
        rows = await self._rows(select(loans).where(loans.c.id == loan_id))
        return _loan(rows[0]) if rows else None

    async def list_loans(self, org_id: str) -> list[Loan]:
        rows = await self._rows(select(loans).where(loans.c.org_id == org_id).order_by(loans.c.id))
        return [_loan(r) for r in rows]

    async def lock_loan(self, loan_id: str) -> Loan | None:
        stmt = select(loans).where(loans.c.id == loan_id).with_for_update(key_share=True)
        rows = await self._rows(stmt)  # FOR NO KEY UPDATE; held until the transaction ends
        return _loan(rows[0]) if rows else None

    async def save_loan(self, loan: Loan) -> None:
        values = loan.model_dump()
        values["required_docs"] = [DocType(d).value for d in loan.required_docs]
        values["stage"] = LoanStage(loan.stage).value
        await _upsert(self.conn, loans, values)

    # documents and rule results
    async def documents(self, loan_id: str) -> list[Document]:
        stmt = (
            select(documents)
            .where(documents.c.loan_id == loan_id)
            .order_by(documents.c.uploaded_at, documents.c.id)
        )
        return [_document(r) for r in await self._rows(stmt)]

    async def save_document(self, doc: Document) -> None:
        await _upsert(
            self.conn,
            documents,
            {
                "id": doc.id,
                "loan_id": doc.loan_id,
                "filename": doc.filename,
                "status": doc.status.value,
                "doc_type": doc.doc_type.value,
                "classification": doc.classification.model_dump(mode="json")
                if doc.classification
                else None,
                "fields": doc.fields.model_dump(mode="json") if doc.fields else None,
                "review_reasons": list(doc.review_reasons),
                "uploaded_by": doc.uploaded_by,
                "uploaded_at": doc.uploaded_at,
            },
        )

    async def results(self, loan_id: str) -> list[RuleResult]:
        stmt = (
            select(rule_results)
            .where(rule_results.c.loan_id == loan_id)
            .order_by(rule_results.c.id)
        )
        return [
            RuleResult(
                code=r["code"],
                severity=r["severity"],
                message=r["message"],
                document_id=r["document_id"],
                borrower_action=r["borrower_action"],
                data=r["data"],
            )
            for r in await self._rows(stmt)
        ]

    async def replace_results(self, loan_id: str, results: list[RuleResult]) -> None:
        await self.conn.execute(delete(rule_results).where(rule_results.c.loan_id == loan_id))
        if results:
            now = self.now()
            await self.conn.execute(
                insert(rule_results),
                [
                    {**r.model_dump(mode="json"), "loan_id": loan_id, "evaluated_at": now}
                    for r in results
                ],
            )

    # message drafts
    async def get_draft(self, draft_id: str) -> MessageDraft | None:
        rows = await self._rows(select(message_drafts).where(message_drafts.c.id == draft_id))
        return _draft(rows[0]) if rows else None

    async def loan_drafts(self, loan_id: str) -> list[MessageDraft]:
        stmt = (
            select(message_drafts)
            .where(message_drafts.c.loan_id == loan_id)
            .order_by(message_drafts.c.created_at, message_drafts.c.id)
        )
        return [_draft(r) for r in await self._rows(stmt)]

    async def org_drafts(self, org_id: str) -> list[MessageDraft]:
        stmt = (
            select(message_drafts)
            .join(loans, loans.c.id == message_drafts.c.loan_id)
            .where(loans.c.org_id == org_id)
            .order_by(message_drafts.c.created_at, message_drafts.c.id)
        )
        return [_draft(r) for r in await self._rows(stmt)]

    async def save_draft(self, draft: MessageDraft) -> None:
        values = draft.model_dump()
        values["status"] = DraftStatus(draft.status).value
        await _upsert(self.conn, message_drafts, values)

    # audit and outbox
    async def audit(
        self,
        actor: str,
        action: str,
        loan_id: str | None = None,
        detail: str = "",
        *,
        org_id: str | None = None,
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
    ) -> None:
        if org_id is None and loan_id is not None:
            rows = await self._rows(select(loans.c.org_id).where(loans.c.id == loan_id))
            org_id = rows[0]["org_id"] if rows else None
        await self.conn.execute(
            insert(audit_events).values(
                at=self.now(),
                actor=actor,
                action=action,
                loan_id=loan_id,
                org_id=org_id,
                detail=mask_for_log(detail)[:500],
                before=before,
                after=after,
            )
        )

    async def audit_events(self, org_id: str, loan_id: str | None = None) -> list[AuditEvent]:
        where = (
            audit_events.c.loan_id == loan_id
            if loan_id is not None
            else audit_events.c.org_id == org_id
        )
        stmt = select(audit_events).where(where).order_by(audit_events.c.id)
        return [
            AuditEvent(
                at=r["at"],
                actor=r["actor"],
                action=r["action"],
                loan_id=r["loan_id"],
                org_id=r["org_id"],
                detail=r["detail"],
                before=r["before"],
                after=r["after"],
            )
            for r in await self._rows(stmt)
        ]

    async def add_outbox(self, loan_id: str, channel: str, body: str) -> None:
        await self.conn.execute(
            insert(outbox_messages).values(
                id=time_sortable_id("O"),
                loan_id=loan_id,
                channel=channel,
                body=body,
                created_at=self.now(),
            )
        )
