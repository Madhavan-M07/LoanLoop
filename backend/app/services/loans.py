"""Use-cases shared by the REST API, the in-app assistant and (via the API) the MCP server."""

from __future__ import annotations

from datetime import timedelta

from pydantic import BaseModel

from app.data.store import Store
from app.domain.models import (
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


def loan_status(store: Store, p: Principal, loan_id: str) -> LoanStatus:
    loan = get_loan_for(store, p, loan_id)
    docs = store.documents[loan.id]
    return LoanStatus(
        loan_id=loan.id,
        stage=loan.stage,
        documents_received=[f"{d.doc_type.value} ({d.status.value})" for d in docs],
        outstanding_items=borrower_actions(store.results[loan.id])
        or ([] if docs else ["Upload your documents to get started."]),
    )


def summarize(store: Store, loan: Loan) -> LoanSummary:
    return LoanSummary(
        loan_id=loan.id,
        borrower_name=loan.borrower_name,
        stage=loan.stage,
        days_since_activity=(store.now() - loan.last_activity_at).days,
        open_issues=sum(r.severity != Severity.PASS for r in store.results[loan.id]),
        pending_drafts=sum(
            d.loan_id == loan.id and d.status == DraftStatus.PENDING for d in store.drafts.values()
        ),
    )


def list_loans(store: Store, p: Principal) -> list[LoanSummary]:
    return [summarize(store, ln) for ln in loans_for(store, p)]


def loan_file(store: Store, p: Principal, loan_id: str) -> LoanFile:
    require_processor(p)
    loan = get_loan_for(store, p, loan_id)
    return LoanFile(
        loan=loan,
        documents=[
            d.model_dump(mode="json", exclude={"fields": {"evidence"}})
            for d in store.documents[loan.id]
        ],
        rule_results=store.results[loan.id],
        pending_drafts=[
            d
            for d in store.drafts.values()
            if d.loan_id == loan.id and d.status == DraftStatus.PENDING
        ],
    )


def stuck_files(store: Store, p: Principal, min_days: int) -> list[LoanSummary]:
    require_processor(p)
    cutoff = store.now() - timedelta(days=min_days)
    return [
        summarize(store, ln)
        for ln in loans_for(store, p)
        if ln.stage != LoanStage.COMPLETE and ln.last_activity_at <= cutoff
    ]


def pending_drafts(store: Store, p: Principal) -> list[MessageDraft]:
    require_processor(p)
    ids = {ln.id for ln in loans_for(store, p)}
    return [
        d for d in store.drafts.values() if d.loan_id in ids and d.status == DraftStatus.PENDING
    ]


def create_draft(store: Store, p: Principal, loan_id: str, body: str) -> MessageDraft:
    """Agents may DRAFT; only a human processor can approve/send."""
    require_processor(p)
    loan = get_loan_for(store, p, loan_id)
    draft = MessageDraft(
        id=store.new_id("M"),
        loan_id=loan.id,
        body=body,
        created_by=p.subject,
        created_at=store.now(),
    )
    store.drafts[draft.id] = draft
    store.audit(p.subject, "draft_created", loan.id, f"{draft.id} awaiting approval")
    return draft


def _draft_for(store: Store, p: Principal, draft_id: str) -> MessageDraft:
    d = store.drafts.get(draft_id)
    if d is None:
        raise NotFound(f"draft {draft_id} not found")
    get_loan_for(store, p, d.loan_id)  # tenant check
    if d.status != DraftStatus.PENDING:
        raise Forbidden(f"draft is {d.status.value}, not pending")
    return d


async def approve_draft(
    store: Store, p: Principal, draft_id: str, notifier: Notifier
) -> MessageDraft:
    require_human_processor(p)
    d = _draft_for(store, p, draft_id)
    d.status, d.decided_by, d.decided_at = DraftStatus.APPROVED, p.subject, store.now()
    store.audit(p.subject, "draft_approved", d.loan_id, d.id)
    loan = store.loans[d.loan_id]
    if await notifier.send(loan, d.body):
        d.status = DraftStatus.SENT
        store.audit("notifier", "message_sent", d.loan_id, d.id)
    return d


def reject_draft(store: Store, p: Principal, draft_id: str) -> MessageDraft:
    require_human_processor(p)
    d = _draft_for(store, p, draft_id)
    d.status, d.decided_by, d.decided_at = DraftStatus.REJECTED, p.subject, store.now()
    store.audit(p.subject, "draft_rejected", d.loan_id, d.id)
    return d
