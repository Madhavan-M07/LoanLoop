"""Multi-agent document pipeline for one uploaded document.

security gate -> PII tokenization -> [classifier agent] -> [extractor agent] -> rehydrate
-> rules engine (deterministic) -> stage update -> [conditions agent] drafts message
-> waits for HUMAN approval.

Phase 3 moves each step into a Temporal activity (durable retries, timers, approval signals);
the step functions stay the same.
"""

from __future__ import annotations

from datetime import date

from app.agents.document_agents import (
    MIN_CLASSIFY_CONFIDENCE,
    classify,
    draft_borrower_message,
    extract,
)
from app.agents.injection import detect_injection
from app.core.pii import tokenize
from app.domain.models import (
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
from app.services.store import Store

MAX_CHARS = 50_000


async def process_document(
    store: Store, llm: LLM, loan: Loan, *, filename: str, text: str, uploaded_by: str
) -> Document:
    doc = Document(
        id=store.new_id("D"),
        loan_id=loan.id,
        filename=filename[:120],
        status=DocStatus.RECEIVED,
        uploaded_by=uploaded_by,
        uploaded_at=store.now(),
    )
    store.documents[loan.id].append(doc)
    store.audit(uploaded_by, "document_uploaded", loan.id, f"{doc.id} {doc.filename}")

    # 1. Security gate (deterministic)
    if not text.strip() or len(text) > MAX_CHARS:
        doc.status = DocStatus.REJECTED
        doc.review_reasons.append("empty or too large")
        store.audit("system", "document_rejected", loan.id, doc.id)
        return await reevaluate(store, llm, loan, doc)
    hits = detect_injection(text)
    if hits:
        doc.review_reasons.append(f"possible prompt injection: {', '.join(hits)[:200]}")
        store.audit("system", "injection_suspected", loan.id, f"{doc.id}: {hits}")

    # 2. PII tokenization: real identifiers never leave our server
    masked, vault = tokenize(text)
    if vault.values:
        store.audit("system", "pii_masked", loan.id, f"{doc.id}: {vault.kinds}")

    # 3. Classifier agent
    cls = await classify(llm, masked)
    store.audit(
        "classifier_agent",
        "classified",
        loan.id,
        f"{doc.id}: {cls.value.doc_type if cls.value else 'FAILED'} "
        f"attempts={cls.attempts} prompt={cls.prompt_version}",
    )
    if not cls.ok or cls.value is None:
        return await _needs_review(
            store, llm, loan, doc, f"classification failed: {cls.errors[-1:]}"
        )
    doc.classification = cls.value
    doc.doc_type = cls.value.doc_type
    if cls.value.doc_type == DocType.UNKNOWN or cls.value.confidence < MIN_CLASSIFY_CONFIDENCE:
        return await _needs_review(
            store, llm, loan, doc, f"low-confidence classification ({cls.value.confidence})"
        )

    # 4. Extractor agent
    ext = await extract(llm, cls.value.doc_type, masked)
    store.audit(
        "extractor_agent",
        "extracted" if ext.ok else "extraction_failed",
        loan.id,
        f"{doc.id}: attempts={ext.attempts} errors={len(ext.errors)}",
    )
    if not ext.ok or ext.value is None:
        return await _needs_review(store, llm, loan, doc, f"extraction failed: {ext.errors[-1:]}")

    # 5. Rehydrate tokens locally, re-validate
    schema = SCHEMA_FOR[cls.value.doc_type]
    doc.fields = schema.model_validate(vault.rehydrate(ext.value.model_dump(mode="json")))  # type: ignore[assignment]
    doc.status = DocStatus.NEEDS_REVIEW if hits else DocStatus.EXTRACTED
    return await reevaluate(store, llm, loan, doc)


async def _needs_review(store: Store, llm: LLM, loan: Loan, doc: Document, reason: str) -> Document:
    doc.status = DocStatus.NEEDS_REVIEW
    doc.review_reasons.append(reason)
    return await reevaluate(store, llm, loan, doc)


async def reevaluate(
    store: Store, llm: LLM, loan: Loan, doc: Document | None = None, today: date | None = None
) -> Document | None:  # type: ignore[return]
    """Run the rules engine over the whole file, update stage, draft a message if needed."""
    today = today or store.now().date()
    docs = store.documents[loan.id]
    results = evaluate_loan(loan, docs, today)
    store.results[loan.id] = results
    actions = borrower_actions(results)

    if actions:
        loan.stage = LoanStage.COLLECTING
    elif any(d.status == DocStatus.NEEDS_REVIEW for d in docs) or any(
        r.severity != Severity.PASS for r in results
    ):
        loan.stage = LoanStage.NEEDS_REVIEW
    else:
        loan.stage = LoanStage.COMPLETE
    loan.last_activity_at = store.now()
    store.audit(
        "rules_engine",
        "evaluated",
        loan.id,
        f"stage={loan.stage} fails={sum(r.severity == Severity.FAIL for r in results)}",
    )

    if actions and docs:  # only chase once the borrower has started sending documents
        await _draft_if_changed(store, llm, loan, actions)
    elif not actions:
        _retire_stale_drafts(store, loan, keep_key=None)  # nothing outstanding any more
    return doc


def _retire_stale_drafts(store: Store, loan: Loan, keep_key: str | None) -> bool:
    """Supersede pending SYSTEM drafts that no longer match the outstanding items, so a processor
    can never approve a stale request. Returns True if a draft with keep_key is still pending."""
    kept = False
    for d in store.drafts.values():
        if d.loan_id != loan.id or d.status != DraftStatus.PENDING or d.request_key is None:
            continue  # human/agent-authored drafts (no request_key) are left for the processor
        if keep_key is not None and d.request_key == keep_key:
            kept = True
            continue
        d.status, d.decided_by, d.decided_at = (
            DraftStatus.REJECTED,
            "system:superseded",
            store.now(),
        )
        store.audit("system", "draft_superseded", loan.id, d.id)
    return kept


async def _draft_if_changed(store: Store, llm: LLM, loan: Loan, actions: list[str]) -> None:
    key = "|".join(actions)
    if _retire_stale_drafts(store, loan, keep_key=key):
        return  # same request already waiting for approval
    body, outcome = await draft_borrower_message(llm, actions)
    draft = MessageDraft(
        id=store.new_id("M"),
        loan_id=loan.id,
        body=body,
        created_by="conditions_agent" if outcome.ok else "system:template",
        created_at=store.now(),
        request_key=key,
    )
    store.drafts[draft.id] = draft
    store.audit(draft.created_by, "draft_created", loan.id, f"{draft.id} awaiting approval")
