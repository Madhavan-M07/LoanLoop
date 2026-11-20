"""In-memory store (Phase 1 slice). Same interface will be backed by PostgreSQL + RLS next.

Contains no data of its own: loans come from the API (later) or a demo file (dev/test).
"""

from __future__ import annotations

import itertools
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from app.core.pii import mask_for_log
from app.domain.models import (
    AuditEvent,
    DocType,
    Document,
    Loan,
    MessageDraft,
    Organization,
    RuleResult,
)

Clock = Callable[[], datetime]


def utc_now() -> datetime:
    return datetime.now(UTC)


class Store:
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

    def new_id(self, prefix: str) -> str:
        return f"{prefix}-{next(self._ids):05d}"

    def audit(
        self,
        actor: str,
        action: str,
        loan_id: str | None = None,
        detail: str = "",
        *,
        org_id: str | None = None,
    ) -> None:
        if org_id is None and loan_id in self.loans:
            org_id = self.loans[loan_id].org_id
        self.audit_log.append(
            AuditEvent(
                at=self.now(),
                actor=actor,
                action=action,
                loan_id=loan_id,
                org_id=org_id,
                detail=mask_for_log(detail)[:500],
            )
        )

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
