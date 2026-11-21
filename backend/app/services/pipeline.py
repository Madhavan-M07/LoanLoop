"""Multi-agent document pipeline for one uploaded document.

security gate -> PII tokenization -> [classifier agent] -> [extractor agent] -> rehydrate
-> rules engine (deterministic) -> stage update -> [conditions agent] drafts message
-> waits for HUMAN approval.

Phase 3 moves each step into a Temporal activity (durable retries, timers, approval signals);
the step functions stay the same.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.agents.document_agents import (
    classify,
    draft_borrower_message,
    extract,
)
from app.data.repository import Repository, Session
from app.domain.models import (
    OPEN_DRAFT_STATUSES,
    SCHEMA_FOR,
    DocStatus,
    DocType,
    Document,
    DraftStatus,
    Loan,
    LoanStage,
    MessageDraft,
    Severity,
)
from app.llm.client import LLM
from app.rules.engine import borrower_actions, evaluate_loan
from app.security.injection import detect_injection
from app.security.pii import tokenize


@dataclass(frozen=True)
class PipelineConfig:
    """Operational knobs, supplied from Settings (never module constants)."""

    min_classify_confidence: float
    max_document_chars: int


async def process_document(
    repo: Repository,
    llm: LLM,
    loan: Loan,
    *,
    filename: str,
    text: str,
    uploaded_by: str,
    cfg: PipelineConfig,
) -> Document:
    """No session is held during the classifier/extractor LLM calls: the document is saved as
    RECEIVED first, the agents run, then one locked session saves the result and re-checks
    the file. `loan` is only used for its id; its current state is re-read under the lock."""
    doc = Document(
        id=repo.new_id("D"),
        loan_id=loan.id,
        filename=filename[:120],
        status=DocStatus.RECEIVED,
        uploaded_by=uploaded_by,
        uploaded_at=repo.now(),
    )
    async with repo.session() as s:
        await s.save_document(doc)
        await s.audit(uploaded_by, "document_uploaded", loan.id, f"{doc.id} {doc.filename}")

    # 1. Security gate (deterministic)
    if not text.strip() or len(text) > cfg.max_document_chars:
        doc.status = DocStatus.REJECTED
        doc.review_reasons.append("empty or too large")
        await repo.audit("system", "document_rejected", loan.id, doc.id)
        return await _finish(repo, llm, loan.id, doc)
    hits = detect_injection(text)
    if hits:
        doc.review_reasons.append(f"possible prompt injection: {', '.join(hits)[:200]}")
        await repo.audit("system", "injection_suspected", loan.id, f"{doc.id}: {hits}")

    # 2. PII tokenization: real identifiers never leave our server
    masked, vault = tokenize(text)
    if vault.values:
        await repo.audit("system", "pii_masked", loan.id, f"{doc.id}: {vault.kinds}")

    # 3. Classifier agent
    cls = await classify(llm, masked)
    await repo.audit(
        "classifier_agent",
        "classified",
        loan.id,
        f"{doc.id}: {cls.value.doc_type if cls.value else 'FAILED'} "
        f"attempts={cls.attempts} prompt={cls.prompt_version} model={cls.model or 'none'}",
    )
    if not cls.ok or cls.value is None:
        return await _needs_review(
            repo, llm, loan.id, doc, f"classification failed: {cls.errors[-1:]}"
        )
    doc.classification = cls.value
    doc.doc_type = cls.value.doc_type
    if cls.value.doc_type == DocType.UNKNOWN or cls.value.confidence < cfg.min_classify_confidence:
        return await _needs_review(
            repo, llm, loan.id, doc, f"low-confidence classification ({cls.value.confidence})"
        )

    # 4. Extractor agent
    ext = await extract(llm, cls.value.doc_type, masked)
    await repo.audit(
        "extractor_agent",
        "extracted" if ext.ok else "extraction_failed",
        loan.id,
        f"{doc.id}: attempts={ext.attempts} errors={len(ext.errors)} "
        f"prompt={ext.prompt_version} model={ext.model or 'none'}",
    )
    if not ext.ok or ext.value is None:
        return await _needs_review(repo, llm, loan.id, doc, f"extraction failed: {ext.errors[-1:]}")

    # 5. Rehydrate tokens locally, re-validate
    schema = SCHEMA_FOR[cls.value.doc_type]
    doc.fields = schema.model_validate(vault.rehydrate(ext.value.model_dump(mode="json")))  # type: ignore[assignment]
    doc.status = DocStatus.NEEDS_REVIEW if hits else DocStatus.EXTRACTED
    return await _finish(repo, llm, loan.id, doc)


async def _needs_review(
    repo: Repository, llm: LLM, loan_id: str, doc: Document, reason: str
) -> Document:
    doc.status = DocStatus.NEEDS_REVIEW
    doc.review_reasons.append(reason)
    return await _finish(repo, llm, loan_id, doc)


async def _finish(repo: Repository, llm: LLM, loan_id: str, doc: Document) -> Document:
    """Save the document's final state and re-check the file, as one locked unit."""
    async with repo.session() as s:
        loan = await s.lock_loan(loan_id)
        if loan is None:
            raise LookupError(f"loan {loan_id} disappeared during processing")
        await s.save_document(doc)
        await _reevaluate_locked(s, repo, llm, loan, touch_activity=True)
    return doc


async def reevaluate(repo: Repository, llm: LLM, loan_id: str, *, touch_activity: bool) -> None:
    """Re-run the rules over the whole file with the organization's CURRENT policy, update the
    stage, and draft a borrower message if something is outstanding.

    touch_activity: True only for real file activity (an upload). A policy change re-checks
    files but must not make them look recently active (that would hide stuck files).

    Runs under the loan's lock: evaluate -> "is this request already pending?" -> draft -> save
    is one unit, so simultaneous uploads can't each create the same draft.
    """
    async with repo.session() as s:
        loan = await s.lock_loan(loan_id)
        if loan is not None:
            await _reevaluate_locked(s, repo, llm, loan, touch_activity=touch_activity)


async def _reevaluate_locked(
    s: Session, repo: Repository, llm: LLM, loan: Loan, *, touch_activity: bool
) -> None:
    docs = await s.documents(loan.id)
    policy = (await s.get_org(loan.org_id)).policy
    results = evaluate_loan(loan, docs, repo.now().date(), policy)
    await s.replace_results(loan.id, results)
    actions = borrower_actions(results)

    if actions:
        loan.stage = LoanStage.COLLECTING
    elif any(d.status == DocStatus.NEEDS_REVIEW for d in docs) or any(
        r.severity != Severity.PASS for r in results
    ):
        loan.stage = LoanStage.NEEDS_REVIEW
    else:
        loan.stage = LoanStage.COMPLETE
    if touch_activity:
        loan.last_activity_at = repo.now()
    await s.save_loan(loan)
    await s.audit(
        "rules_engine",
        "evaluated",
        loan.id,
        f"stage={loan.stage} fails={sum(r.severity == Severity.FAIL for r in results)}",
    )

    if actions and docs:  # only chase once the borrower has started sending documents
        await _draft_if_changed(s, repo, llm, loan, actions)
    elif not actions:
        await _retire_stale_drafts(s, repo, loan, keep_key=None)  # nothing outstanding any more


async def _retire_stale_drafts(
    s: Session, repo: Repository, loan: Loan, keep_key: str | None
) -> bool:
    """Supersede open SYSTEM drafts (pending or send-failed) that no longer match the outstanding
    items, so a processor can never approve or retry a stale request. Returns True if a draft
    with keep_key is still open."""
    kept = False
    for d in await s.loan_drafts(loan.id):
        if d.status not in OPEN_DRAFT_STATUSES or d.request_key is None:
            continue  # human/agent-authored drafts (no request_key) are left for the processor
        if keep_key is not None and d.request_key == keep_key:
            kept = True
            continue
        d.status, d.decided_by, d.decided_at = (
            DraftStatus.REJECTED,
            "system:superseded",
            repo.now(),
        )
        await s.save_draft(d)
        await s.audit("system", "draft_superseded", loan.id, d.id)
    return kept


async def _draft_if_changed(
    s: Session, repo: Repository, llm: LLM, loan: Loan, actions: list[str]
) -> None:
    key = "|".join(actions)
    if await _retire_stale_drafts(s, repo, loan, keep_key=key):
        return  # same request already waiting for approval
    # KNOWN TRADE-OFF: this LLM call runs while the loan is locked (and, with Postgres, inside
    # the transaction), for up to the LLM timeout. Only this loan waits. Removed when drafting
    # moves into a Temporal activity (roadmap Phase 3).
    body, outcome = await draft_borrower_message(llm, actions)
    draft = MessageDraft(
        id=repo.new_id("M"),
        loan_id=loan.id,
        body=body,
        created_by="conditions_agent" if outcome.ok else "system:template",
        created_at=repo.now(),
        request_key=key,
    )
    await s.save_draft(draft)
    await s.audit(draft.created_by, "draft_created", loan.id, f"{draft.id} awaiting approval")
