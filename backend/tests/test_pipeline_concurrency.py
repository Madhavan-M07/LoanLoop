"""Concurrent uploads for one loan must not create duplicate borrower drafts.

Real-world shape: a borrower sends several photos at once over WhatsApp/Telegram. Before the fix,
each upload checked "is a draft already pending?", then awaited the LLM, then saved, so both
uploads passed the check and the processor got two identical drafts (hurts O1).
"""

import asyncio
from datetime import date
from typing import Any

from app.domain.models import OPEN_DRAFT_STATUSES
from app.llm.client import ChatResult
from app.llm.fake import OfflineLLM
from app.services.pipeline import PipelineConfig, process_document
from tests import synthetic

CFG = PipelineConfig(min_classify_confidence=0.6, max_document_chars=50_000)


class SlowLLM:
    """Yields to the event loop on every call, like a real network call, to force interleaving."""

    def __init__(self) -> None:
        self.inner = OfflineLLM()

    async def chat(self, messages: list[dict[str, Any]], **kw: Any) -> ChatResult:
        await asyncio.sleep(0.01)
        return await self.inner.chat(messages, **kw)


def _open_drafts(store, loan_id: str) -> list:
    return [
        d for d in store.drafts.values() if d.loan_id == loan_id and d.status in OPEN_DRAFT_STATUSES
    ]


async def test_simultaneous_uploads_create_one_draft(store):
    loan = store.loans["L-1001"]
    llm = SlowLLM()
    stub = synthetic.paystub(
        employee="Priya Sharma", employer="Acme Robotics Inc.", pay_date=date(2026, 9, 30)
    )
    w2 = synthetic.w2(employee="Priya Sharma", employer="Acme Robotics LLC", tax_year=2025)

    await asyncio.gather(
        process_document(
            store, llm, loan, filename="stub.txt", text=stub, uploaded_by="b", cfg=CFG
        ),
        process_document(store, llm, loan, filename="w2.txt", text=w2, uploaded_by="b", cfg=CFG),
    )

    drafts = _open_drafts(store, "L-1001")
    assert len(drafts) == 1, [d.body for d in drafts]
    assert len(store.documents["L-1001"]) == 2  # both documents still processed


async def test_different_loans_are_not_blocked_by_each_other(store):
    """The lock is per loan: work on one file never waits for another."""
    llm = SlowLLM()
    stub = synthetic.paystub(
        employee="Priya Sharma", employer="Acme Robotics Inc.", pay_date=date(2026, 9, 30)
    )
    a, b = store.loans["L-1001"], store.loans["L-1002"]
    await asyncio.gather(
        process_document(store, llm, a, filename="s.txt", text=stub, uploaded_by="b", cfg=CFG),
        process_document(store, llm, b, filename="s.txt", text=stub, uploaded_by="b", cfg=CFG),
    )
    assert len(_open_drafts(store, "L-1001")) == 1
    assert len(_open_drafts(store, "L-1002")) == 1
