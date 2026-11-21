"""Load demo organizations and loans into ANY repository (memory or Postgres). Dev/test only:
the demo file is refused in prod by Settings, and this never runs unless explicitly called.

Idempotent and non-destructive: organizations and loans that already exist are left exactly
as they are (stage, policy edits, documents, drafts, audit history). Only missing ones are added.
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
    """Returns (organizations, loans) newly added."""
    orgs = [Organization.model_validate(o) for o in demo.get("organizations", [])]
    loans = demo_loans(demo.get("loans", []), repo.now())
    added_orgs = added_loans = 0
    async with repo.session() as s:
        for org in orgs:
            try:
                await s.get_org(org.id)
            except LookupError:
                await s.save_org(org)
                added_orgs += 1
        for loan in loans:
            if await s.get_loan(loan.id) is not None:
                continue
            await s.get_org(loan.org_id)  # raises: loans need a configured organization
            await s.save_loan(loan)
            added_loans += 1
    return added_orgs, added_loans


async def _main() -> None:
    from app.core.config import get_settings
    from app.data.db import Database
    from app.data.postgres import PostgresRepository
    from app.data.store import utc_now

    settings = get_settings()  # reads backend/.env; demo data is refused in prod
    if settings.database_url is None:
        raise SystemExit("LOANLOOP_DATABASE_URL is not set; nothing to seed.")
    demo = settings.demo_data()
    if demo is None:
        raise SystemExit("LOANLOOP_DEMO_DATA_PATH is not set; nothing to load.")
    db = Database(settings.database_url.get_secret_value(), settings.database_timeout_s)
    try:
        orgs, loans = await load_demo(PostgresRepository(db.engine, utc_now), demo)
    finally:
        await db.dispose()
    print(f"Added {orgs} organizations and {loans} demo loans (synthetic; existing rows kept).")


if __name__ == "__main__":  # from backend/:  uv run python -m app.data.seed
    import asyncio

    asyncio.run(_main())
