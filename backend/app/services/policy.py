"""Organization lender policy: read (processors) and change (human admins only)."""

from __future__ import annotations

from app.data.repository import Repository
from app.domain.models import LenderPolicy, Principal
from app.llm.client import LLM
from app.services.access import loans_for, require_admin, require_processor
from app.services.pipeline import reevaluate


async def get_policy(repo: Repository, p: Principal) -> LenderPolicy:
    require_processor(p)
    async with repo.session() as s:
        return (await s.get_org(p.org_id)).policy


def _changes(old: LenderPolicy, new: LenderPolicy) -> list[str]:
    before, after = old.model_dump(), new.model_dump()
    return [f"{k}: {before[k]} -> {after[k]}" for k in after if before[k] != after[k]]


async def update_policy(
    repo: Repository, llm: LLM, p: Principal, new: LenderPolicy
) -> LenderPolicy:
    """Replace the organization's policy, audit the change, and re-check open loan files so no
    result is computed against an outdated rule."""
    require_admin(p)
    async with repo.session() as s:
        org = await s.get_org(p.org_id)
        changes = _changes(org.policy, new)
        if not changes:
            return org.policy
        before = org.policy.model_dump(mode="json")
        org.policy = new
        await s.save_org(org)
        await s.audit(
            p.subject,
            "policy_updated",
            detail="; ".join(changes),
            org_id=org.id,
            before=before,
            after=new.model_dump(mode="json"),
        )
        to_recheck = [ln.id for ln in await loans_for(s, p) if await s.documents(ln.id)]
    for loan_id in to_recheck:  # each file re-checked under its own lock
        await reevaluate(repo, llm, loan_id, touch_activity=False)
    return new
