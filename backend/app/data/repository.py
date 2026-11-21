"""Storage interface. Services depend on THIS, never on a concrete store.

Two implementations share it: the in-memory `Store` (tests, demo) and PostgreSQL (next).

Contract every implementation must honour (the in-memory store enforces it too, so a service
that breaks it fails tests long before Postgres is involved):
- Reads return COPIES. Changing a returned object changes nothing until you call `save_*`.
- All work happens inside `async with repo.session() as s:`, which is one transaction.
- `s.lock_loan(id)` serializes work on one loan file until the session ends (in memory: an
  asyncio lock; Postgres: `SELECT ... FOR UPDATE`). Other loans are never blocked.
- Never hold a session across a network call you can avoid (LLM, Telegram): it holds the
  transaction and, after `lock_loan`, the loan's lock. Known exception, documented at the call
  site: drafting the borrower message inside `reevaluate` (removed by the Temporal workflow).
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from datetime import datetime
from typing import Protocol

from app.domain.models import (
    AuditEvent,
    Document,
    Loan,
    MessageDraft,
    Organization,
    RuleResult,
)

Clock = Callable[[], datetime]


class Session(Protocol):
    # organizations
    async def get_org(self, org_id: str) -> Organization: ...
    async def save_org(self, org: Organization) -> None: ...

    # loans
    async def get_loan(self, loan_id: str) -> Loan | None: ...
    async def list_loans(self, org_id: str) -> list[Loan]: ...
    async def lock_loan(self, loan_id: str) -> Loan | None:
        """Lock the loan until the session ends, then return its CURRENT state."""
        ...

    async def save_loan(self, loan: Loan) -> None: ...

    # documents and rule results
    async def documents(self, loan_id: str) -> list[Document]: ...
    async def save_document(self, doc: Document) -> None: ...
    async def results(self, loan_id: str) -> list[RuleResult]: ...
    async def replace_results(self, loan_id: str, results: list[RuleResult]) -> None: ...

    # message drafts
    async def get_draft(self, draft_id: str) -> MessageDraft | None: ...
    async def loan_drafts(self, loan_id: str) -> list[MessageDraft]: ...
    async def org_drafts(self, org_id: str) -> list[MessageDraft]: ...
    async def save_draft(self, draft: MessageDraft) -> None: ...

    # audit (append-only) and outbound messages
    async def audit(
        self,
        actor: str,
        action: str,
        loan_id: str | None = None,
        detail: str = "",
        *,
        org_id: str | None = None,
    ) -> None: ...
    async def audit_events(self, org_id: str, loan_id: str | None = None) -> list[AuditEvent]: ...
    async def add_outbox(self, loan_id: str, channel: str, body: str) -> None: ...


class Repository(Protocol):
    now: Clock

    def new_id(self, prefix: str) -> str: ...
    def session(self) -> AbstractAsyncContextManager[Session]: ...

    async def audit(
        self,
        actor: str,
        action: str,
        loan_id: str | None = None,
        detail: str = "",
        *,
        org_id: str | None = None,
    ) -> None:
        """One audit row in its own short session (for steps that run outside a session)."""
        ...
