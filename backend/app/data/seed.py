"""Load demo organizations and loans into ANY repository (memory or Postgres). Dev/test only:
the demo file is refused in prod by Settings, and this never runs unless explicitly called.

Idempotent: saving is an upsert, so loading twice leaves one copy (documents, drafts and audit
history already in the database are kept).
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Any

from app.data.repository import Repository
from app.domain.models import DocType, Loan, Organization


def demo_loans(raw_loans: list[dict[str, Any]], now: Any) -> list[Loan]:
    """`days_idle` lets demo data express recency relative to now."""
    out = []
    for raw in raw_loans:
        days_idle = int(raw.get("days_idle", 0))
        out.append(
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
    return out


async def load_demo(repo: Repository, demo: dict[str, Any]) -> tuple[int, int]:
    """Returns (organizations, loans) loaded."""
    orgs = [Organization.model_validate(o) for o in demo.get("organizations", [])]
    loans = demo_loans(demo.get("loans", []), repo.now())
    async with repo.session() as s:
        for org in orgs:
            await s.save_org(org)
        known = {o.id for o in orgs}
        for loan in loans:
            if loan.org_id not in known:
                await s.get_org(loan.org_id)  # raises: loans need a configured organization
            await s.save_loan(loan)
    return len(orgs), len(loans)
