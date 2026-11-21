"""In-memory implementation of the storage interface (app/data/repository.py).

Used by tests and the demo. Follows the same contract as PostgreSQL: reads return copies, so a
service that forgets to `save_*` loses its change here exactly as it would in the database.

Contains no data of its own: loans come from the API (later) or a demo file (dev/test).
"""

from __future__ import annotations

import asyncio
import itertools
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, TypeVar

from pydantic import BaseModel

from app.data.repository import Clock
from app.domain.models import (
    AuditEvent,
    DocType,
    Document,
    Loan,
    MessageDraft,
    Organization,
    RuleResult,
)
from app.security.pii import mask_for_log

M = TypeVar("M", bound=BaseModel)


def utc_now() -> datetime:
    return datetime.now(UTC)


def _copy(m: M) -> M:
    return m.model_copy(deep=True)


class Store:
    """The data lives in these attributes (tests read them directly). Services must go through
    `session()`; nothing outside this module and tests touches the attributes."""

    def __init__(self, clock: Clock = utc_now) -> None:
        self.now = clock
        self.orgs: dict[str, Organization] = {}
        self.loans: dict[str, Loan] = {}
        self.documents: dict[str, list[Document]] = {}
        self.results: dict[str, list[RuleResult]] = {}
        self.drafts: dict[str, MessageDraft] = {}
        self.audit_log: list[AuditEvent] = []
        self.outbox: list[dict[str, str]] = []
        self._ids = itertools.count(1)
        self._loan_locks: dict[str, asyncio.Lock] = {}

    def new_id(self, prefix: str) -> str:
        return f"{prefix}-{next(self._ids):05d}"

    @asynccontextmanager
    async def session(self) -> AsyncIterator[MemorySession]:
        s = MemorySession(self)
        try:
            yield s
        finally:
            s.release_locks()

    async def audit(
        self,
        actor: str,
        action: str,
        loan_id: str | None = None,
        detail: str = "",
        *,
        org_id: str | None = None,
    ) -> None:
        async with self.session() as s:
            await s.audit(actor, action, loan_id, detail, org_id=org_id)

    # ---- loading (demo file / tests) ----------------------------------------------------

    def org(self, org_id: str) -> Organization:
        """Every loan belongs to a known organization; a missing one is a data error."""
        try:
            return self.orgs[org_id]
        except KeyError:
            raise LookupError(f"organization {org_id} is not configured") from None

    def add_loan(self, loan: Loan) -> None:
        self.org(loan.org_id)  # refuse loans for unknown organizations
        self.loans[loan.id] = loan
        self.documents.setdefault(loan.id, [])
        self.results.setdefault(loan.id, [])


class MemorySession:
    def __init__(self, store: Store) -> None:
        self.store = store
        self._held: list[asyncio.Lock] = []
        self._held_ids: set[str] = set()

    def release_locks(self) -> None:
        for lock in reversed(self._held):
            lock.release()
        self._held.clear()
        self._held_ids.clear()

    # organizations
    async def get_org(self, org_id: str) -> Organization:
        return _copy(self.store.org(org_id))

    async def save_org(self, org: Organization) -> None:
        self.store.orgs[org.id] = _copy(org)

    # loans
    async def get_loan(self, loan_id: str) -> Loan | None:
        loan = self.store.loans.get(loan_id)
        return _copy(loan) if loan else None

    async def list_loans(self, org_id: str) -> list[Loan]:
        return [_copy(ln) for ln in self.store.loans.values() if ln.org_id == org_id]

    async def lock_loan(self, loan_id: str) -> Loan | None:
        if loan_id not in self._held_ids:  # re-locking within one session is a no-op
            lock = self.store._loan_locks.setdefault(loan_id, asyncio.Lock())
            await lock.acquire()
            self._held.append(lock)
            self._held_ids.add(loan_id)
        return await self.get_loan(loan_id)

    async def save_loan(self, loan: Loan) -> None:
        self.store.add_loan(_copy(loan))

    # documents and rule results
    async def documents(self, loan_id: str) -> list[Document]:
        return [_copy(d) for d in self.store.documents.get(loan_id, [])]

    async def save_document(self, doc: Document) -> None:
        docs = self.store.documents.setdefault(doc.loan_id, [])
        for i, existing in enumerate(docs):
            if existing.id == doc.id:
                docs[i] = _copy(doc)
                return
        docs.append(_copy(doc))

    async def results(self, loan_id: str) -> list[RuleResult]:
        return [_copy(r) for r in self.store.results.get(loan_id, [])]

    async def replace_results(self, loan_id: str, results: list[RuleResult]) -> None:
        self.store.results[loan_id] = [_copy(r) for r in results]

    # message drafts
    async def get_draft(self, draft_id: str) -> MessageDraft | None:
        d = self.store.drafts.get(draft_id)
        return _copy(d) if d else None

    async def loan_drafts(self, loan_id: str) -> list[MessageDraft]:
        return [_copy(d) for d in self.store.drafts.values() if d.loan_id == loan_id]

    async def org_drafts(self, org_id: str) -> list[MessageDraft]:
        ids = {ln.id for ln in self.store.loans.values() if ln.org_id == org_id}
        return [_copy(d) for d in self.store.drafts.values() if d.loan_id in ids]

    async def save_draft(self, draft: MessageDraft) -> None:
        self.store.drafts[draft.id] = _copy(draft)

    # audit and outbox
    async def audit(
        self,
        actor: str,
        action: str,
        loan_id: str | None = None,
        detail: str = "",
        *,
        org_id: str | None = None,
    ) -> None:
        if org_id is None and loan_id in self.store.loans:
            org_id = self.store.loans[loan_id].org_id
        self.store.audit_log.append(
            AuditEvent(
                at=self.store.now(),
                actor=actor,
                action=action,
                loan_id=loan_id,
                org_id=org_id,
                detail=mask_for_log(detail)[:500],
            )
        )

    async def audit_events(self, org_id: str, loan_id: str | None = None) -> list[AuditEvent]:
        if loan_id is not None:
            return [_copy(e) for e in self.store.audit_log if e.loan_id == loan_id]
        return [_copy(e) for e in self.store.audit_log if e.org_id == org_id]

    async def add_outbox(self, loan_id: str, channel: str, body: str) -> None:
        self.store.outbox.append({"loan_id": loan_id, "channel": channel, "body": body})


def load_orgs(store: Store, orgs: list[dict[str, Any]]) -> Store:
    for raw in orgs:
        org = Organization.model_validate(raw)  # policy is required and validated
        store.orgs[org.id] = org
    return store


def load_loans(store: Store, loans: list[dict[str, Any]]) -> Store:
    """Load loans from data (demo file today, admin API / Postgres next). `days_idle` lets demo
    data express recency relative to now."""
    now = store.now()
    for raw in loans:
        days_idle = int(raw.get("days_idle", 0))
        store.add_loan(
            Loan(
                **{
                    k: v
                    for k, v in raw.items()
                    if k not in {"days_idle", "monthly_debts", "required_docs"}
                },
                monthly_debts=Decimal(str(raw["monthly_debts"])),
                required_docs=[DocType(d) for d in raw["required_docs"]],
                created_at=now - timedelta(days=days_idle),
                last_activity_at=now - timedelta(days=days_idle),
            )
        )
    return store
