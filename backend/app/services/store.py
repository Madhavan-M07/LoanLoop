"""In-memory store (Phase 1 slice). Same interface will be backed by PostgreSQL + RLS next.

Synthetic seed data only.
"""

from __future__ import annotations

import itertools
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.core.pii import mask_for_log
from app.domain.models import (
    AuditEvent,
    DocType,
    Document,
    Loan,
    MessageDraft,
    RuleResult,
)

Clock = Callable[[], datetime]


def utc_now() -> datetime:
    return datetime.now(UTC)


class Store:
    def __init__(self, clock: Clock = utc_now) -> None:
        self.now = clock
        self.loans: dict[str, Loan] = {}
        self.documents: dict[str, list[Document]] = {}
        self.results: dict[str, list[RuleResult]] = {}
        self.drafts: dict[str, MessageDraft] = {}
        self.audit_log: list[AuditEvent] = []
        self.outbox: list[dict[str, str]] = []
        self._ids = itertools.count(1)

    def new_id(self, prefix: str) -> str:
        return f"{prefix}-{next(self._ids):05d}"

    def audit(self, actor: str, action: str, loan_id: str | None = None, detail: str = "") -> None:
        self.audit_log.append(
            AuditEvent(
                at=self.now(),
                actor=actor,
                action=action,
                loan_id=loan_id,
                detail=mask_for_log(detail)[:500],
            )
        )

    def add_loan(self, loan: Loan) -> None:
        self.loans[loan.id] = loan
        self.documents.setdefault(loan.id, [])
        self.results.setdefault(loan.id, [])


def seed_demo(store: Store) -> Store:
    now = store.now()
    all_docs = [DocType.PAYSTUB, DocType.W2, DocType.BANK_STATEMENT]
    for loan_id, org, name, subject, debts, days_idle in [
        ("L-1001", "acme", "Priya Sharma", "bor-priya", "1450.00", 0),
        ("L-1002", "acme", "John Carter", "bor-john", "900.00", 4),
        ("L-2001", "beta", "Meera Iyer", "bor-meera", "2100.00", 1),
    ]:
        store.add_loan(
            Loan(
                id=loan_id,
                org_id=org,
                borrower_name=name,
                borrower_subject=subject,
                loan_officer="lo-sam" if org == "acme" else "lo-kim",
                monthly_debts=Decimal(debts),
                required_docs=all_docs,
                created_at=now - timedelta(days=days_idle + 3),
                last_activity_at=now - timedelta(days=days_idle),
            )
        )
    return store
