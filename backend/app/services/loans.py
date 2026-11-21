"""Use-cases shared by the REST API, the in-app assistant and (via the API) the MCP server."""

from __future__ import annotations

from datetime import timedelta

from pydantic import BaseModel

from app.data.repository import Repository, Session
from app.domain.models import (
    OPEN_DRAFT_STATUSES,
    DraftStatus,
    Loan,
    LoanStage,
    LoanStatus,
    MessageDraft,
    Principal,
    RuleResult,
    Severity,
)
from app.integrations.notifier import Notifier
from app.rules.engine import borrower_actions
from app.services.access import (
    Forbidden,
    NotFound,
    get_loan_for,
    loans_for,
    require_human_processor,
    require_processor,
)


class LoanSummary(BaseModel):
    loan_id: str
    borrower_name: str
    stage: LoanStage
    days_since_activity: int
    open_issues: int
    pending_drafts: int


class LoanFile(BaseModel):
    loan: Loan
    documents: list[dict[str, object]]
    rule_results: list[RuleResult]
    pending_drafts: list[MessageDraft]


async def loan_status(repo: Repository, p: Principal, loan_id: str) -> LoanStatus:
    async with repo.session() as s:
        loan = await get_loan_for(s, p, loan_id)
        docs = await s.documents(loan.id)
        results = await s.results(loan.id)
    return LoanStatus(
        loan_id=loan.id,
        stage=loan.stage,
        documents_received=[f"{d.doc_type.value} ({d.status.value})" for d in docs],
        outstanding_items=borrower_actions(results)
        or ([] if docs else ["Upload your documents to get started."]),
    )


async def _summarize(s: Session, repo: Repository, loan: Loan) -> LoanSummary:
    results = await s.results(loan.id)
    drafts = await s.loan_drafts(loan.id)
    return LoanSummary(
        loan_id=loan.id,
        borrower_name=loan.borrower_name,
        stage=loan.stage,
        days_since_activity=(repo.now() - loan.last_activity_at).days,
        open_issues=sum(r.severity != Severity.PASS for r in results),
        pending_drafts=sum(d.status in OPEN_DRAFT_STATUSES for d in drafts),
    )


async def list_loans(repo: Repository, p: Principal) -> list[LoanSummary]:
    async with repo.session() as s:
        return [await _summarize(s, repo, ln) for ln in await loans_for(s, p)]


async def loan_file(repo: Repository, p: Principal, loan_id: str) -> LoanFile:
    require_processor(p)
    async with repo.session() as s:
        loan = await get_loan_for(s, p, loan_id)
        docs = await s.documents(loan.id)
        results = await s.results(loan.id)
        drafts = await s.loan_drafts(loan.id)
    return LoanFile(
        loan=loan,
        documents=[d.model_dump(mode="json", exclude={"fields": {"evidence"}}) for d in docs],
        rule_results=results,
        pending_drafts=[d for d in drafts if d.status in OPEN_DRAFT_STATUSES],
    )


async def stuck_files(repo: Repository, p: Principal, min_days: int) -> list[LoanSummary]:
    require_processor(p)
    cutoff = repo.now() - timedelta(days=min_days)
    async with repo.session() as s:
        return [
            await _summarize(s, repo, ln)
            for ln in await loans_for(s, p)
            if ln.stage != LoanStage.COMPLETE and ln.last_activity_at <= cutoff
        ]


async def pending_drafts(repo: Repository, p: Principal) -> list[MessageDraft]:
    require_processor(p)
    async with repo.session() as s:
        ids = {ln.id for ln in await loans_for(s, p)}
        return [
            d
            for d in await s.org_drafts(p.org_id)
            if d.loan_id in ids and d.status in OPEN_DRAFT_STATUSES
        ]


async def create_draft(repo: Repository, p: Principal, loan_id: str, body: str) -> MessageDraft:
    """Agents may DRAFT; only a human processor can approve/send."""
    require_processor(p)
    async with repo.session() as s:
        loan = await get_loan_for(s, p, loan_id)
        draft = MessageDraft(
            id=repo.new_id("M"),
            loan_id=loan.id,
            body=body,
            created_by=p.subject,
            created_at=repo.now(),
        )
        await s.save_draft(draft)
        await s.audit(p.subject, "draft_created", loan.id, f"{draft.id} awaiting approval")
    return draft


async def _open_draft_locked(s: Session, p: Principal, draft_id: str) -> MessageDraft:
    """Find the draft, check the caller may see its loan, LOCK that loan, then re-read the
    draft: two simultaneous approvals can't both pass the "still open?" check."""
    d = await s.get_draft(draft_id)
    if d is None:
        raise NotFound(f"draft {draft_id} not found")
    await get_loan_for(s, p, d.loan_id)  # tenant check
    await s.lock_loan(d.loan_id)
    d = await s.get_draft(draft_id)
    if d is None or d.status not in OPEN_DRAFT_STATUSES:
        status = d.status.value if d else "gone"
        raise Forbidden(f"draft is {status}; it can no longer be approved or rejected")
    return d


async def approve_draft(
    repo: Repository, p: Principal, draft_id: str, notifier: Notifier
) -> MessageDraft:
    require_human_processor(p)
    async with repo.session() as s:
        d = await _open_draft_locked(s, p, draft_id)
        status_before = d.status
        d.status, d.decided_by, d.decided_at = DraftStatus.APPROVED, p.subject, repo.now()
        await s.save_draft(d)
        await s.audit(
            p.subject,
            "draft_approved",
            d.loan_id,
            d.id,
            before={"status": status_before.value},
            after={"status": d.status.value},
        )
        loan = await s.get_loan(d.loan_id)
    assert loan is not None  # loans are never deleted

    # Sent OUTSIDE the transaction: a slow channel must not hold the database.
    reason = "refused by channel"
    try:
        delivered = await notifier.send(loan, d.body)
    except Exception as e:  # any delivery failure must land back in the inbox, never strand it
        delivered, reason = False, type(e).__name__

    async with repo.session() as s:
        d.status = DraftStatus.SENT if delivered else DraftStatus.SEND_FAILED
        await s.save_draft(d)
        await s.audit(
            "notifier",
            "message_sent" if delivered else "message_send_failed",
            d.loan_id,
            d.id if delivered else f"{d.id}: {reason}",
            before={"status": DraftStatus.APPROVED.value},
            after={"status": d.status.value},
        )
    return d


async def reject_draft(repo: Repository, p: Principal, draft_id: str) -> MessageDraft:
    require_human_processor(p)
    async with repo.session() as s:
        d = await _open_draft_locked(s, p, draft_id)
        status_before = d.status
        d.status, d.decided_by, d.decided_at = DraftStatus.REJECTED, p.subject, repo.now()
        await s.save_draft(d)
        await s.audit(
            p.subject,
            "draft_rejected",
            d.loan_id,
            d.id,
            before={"status": status_before.value},
            after={"status": d.status.value},
        )
    return d
