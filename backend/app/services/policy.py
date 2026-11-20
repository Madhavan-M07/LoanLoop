"""Organization lender policy: read (processors) and change (human admins only)."""

from __future__ import annotations

from app.domain.models import LenderPolicy, Principal
from app.llm.client import LLM
from app.services.access import loans_for, require_admin, require_processor
from app.services.pipeline import reevaluate
from app.services.store import Store


def get_policy(store: Store, p: Principal) -> LenderPolicy:
    require_processor(p)
    return store.org(p.org_id).policy


def _changes(old: LenderPolicy, new: LenderPolicy) -> list[str]:
    before, after = old.model_dump(), new.model_dump()
    return [f"{k}: {before[k]} -> {after[k]}" for k in after if before[k] != after[k]]


async def update_policy(store: Store, llm: LLM, p: Principal, new: LenderPolicy) -> LenderPolicy:
    """Replace the organization's policy, audit the change, and re-check open loan files so no
    result is computed against an outdated rule."""
    require_admin(p)
    org = store.org(p.org_id)
    changes = _changes(org.policy, new)
    if not changes:
        return org.policy
    org.policy = new
    store.audit(p.subject, "policy_updated", detail="; ".join(changes), org_id=org.id)
    for loan in loans_for(store, p):
        if store.documents[loan.id]:
            await reevaluate(store, llm, loan, touch_activity=False)
    return new
