"""The three structured agents: classifier, extractor, conditions writer (no tools)."""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

from app.agents.structured import StepOutcome, document_block, run_structured
from app.domain.models import SCHEMA_FOR, Classification, DocType
from app.llm.client import LLM


async def classify(llm: LLM, masked_text: str) -> StepOutcome[Classification]:
    return await run_structured(
        llm, agent="classifier", schema=Classification, data_block=document_block(masked_text)
    )


async def extract(llm: LLM, doc_type: DocType, masked_text: str) -> StepOutcome[BaseModel]:
    schema = SCHEMA_FOR[doc_type]

    def sanity(v: BaseModel) -> list[str]:
        problems = []
        for name in ("employer_name", "employee_name", "account_holder", "bank_name"):
            if hasattr(v, name) and not str(getattr(v, name)).strip():
                problems.append(f"{name} is empty")
        return problems

    return await run_structured(
        llm,
        agent="extractor",
        schema=schema,  # type: ignore[arg-type]
        data_block=document_block(masked_text),
        extra_instructions=f"\nDocument type: {doc_type.value}",
        validate=sanity,
    )


class BorrowerMessage(BaseModel):
    message: str = Field(min_length=20, max_length=1000)


_FORBIDDEN = re.compile(r"(?i)\b(approved|guarantee[d]?|pre-?approved|your rate|denied|declined)\b")
_TOKEN = re.compile(r"<[A-Z]+_\d+>")


def fallback_message(items: list[str]) -> str:
    """Deterministic template used when the LLM is unavailable or its draft fails checks."""
    lines = "\n".join(f"• {i}" for i in items)
    return (
        f"Hi! To keep your loan file moving, we still need:\n{lines}\n"
        "You can reply here with a photo or PDF. Thank you!"
    )


async def draft_borrower_message(
    llm: LLM, items: list[str]
) -> tuple[str, StepOutcome[BorrowerMessage]]:
    """Returns (message, outcome). Items are rule-engine outputs: no PII, no free text from docs."""

    def sanity(v: BorrowerMessage) -> list[str]:
        problems = []
        if _FORBIDDEN.search(v.message):
            problems.append("message makes a promise/decision statement (forbidden)")
        if _TOKEN.search(v.message):
            problems.append("message contains a PII token")
        return problems

    block = "Outstanding items:\n" + "\n".join(f"- {i}" for i in items)
    outcome = await run_structured(
        llm, agent="conditions", schema=BorrowerMessage, data_block=block, validate=sanity
    )
    return (outcome.value.message if outcome.value else fallback_message(items)), outcome
