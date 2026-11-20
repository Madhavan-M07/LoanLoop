"""Authorization: who may see which loan. Enforced server-side for every API call and MCP tool.

Rule: a loan outside your scope is reported as NOT FOUND (never "forbidden"), so callers can't
probe which loan IDs exist.
"""

from __future__ import annotations

from app.data.store import Store
from app.domain.models import Loan, Principal, Scope


class NotFound(Exception):
    pass


class Forbidden(Exception):
    pass


def can_access(p: Principal, loan: Loan) -> bool:
    if loan.org_id != p.org_id:
        return False
    if p.scope == Scope.PROCESSOR:
        return True
    return p.scope == Scope.BORROWER and p.loan_id == loan.id


def get_loan_for(store: Store, p: Principal, loan_id: str) -> Loan:
    loan = store.loans.get(loan_id)
    if loan is None or not can_access(p, loan):
        raise NotFound(f"loan {loan_id} not found")
    return loan


def loans_for(store: Store, p: Principal) -> list[Loan]:
    return [ln for ln in store.loans.values() if can_access(p, ln)]


def require_processor(p: Principal) -> None:
    if p.scope != Scope.PROCESSOR:
        raise Forbidden("processor scope required")


def require_human_processor(p: Principal) -> None:
    """Final actions (approve/send) are human-only: no agent identity may perform them."""
    require_processor(p)
    if p.via_agent:
        raise Forbidden(f"agents ({p.via_agent}) cannot perform this action; a human must")


def require_admin(p: Principal) -> None:
    """Organization settings: human processors with the admin flag only."""
    require_human_processor(p)
    if not p.is_admin:
        raise Forbidden("organization admin required")
