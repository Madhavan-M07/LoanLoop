"""Test and offline LLMs.

- ScriptedLLM: returns pre-recorded responses in order (unit tests).
- OfflineLLM: a small deterministic heuristic "model" so the whole system runs with zero API
  keys (local demo, CI). It is clearly NOT an AI: real quality is measured with real providers
  in evals/. Selected with LOANLOOP_LLM_MODE=offline.
"""

from __future__ import annotations

import json
import re
from typing import Any

from app.llm.client import ChatResult, LLMError, ToolCall


class ScriptedLLM:
    def __init__(self, responses: list[ChatResult | Exception]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        json_mode: bool = False,
    ) -> ChatResult:
        self.calls.append({"messages": [dict(m) for m in messages], "tools": tools})
        if not self.responses:
            raise LLMError("ScriptedLLM: no more responses")
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def text(content: str) -> ChatResult:
    return ChatResult(content=content)


def tool_call(name: str, args: dict[str, Any] | str, call_id: str = "call_1") -> ChatResult:
    raw = args if isinstance(args, str) else json.dumps(args)
    return ChatResult(content=None, tool_calls=[ToolCall(id=call_id, name=name, arguments=raw)])


def _between(pattern: str, s: str) -> str | None:
    m = re.search(pattern, s, re.I | re.M)
    return m.group(1).strip() if m else None


class OfflineLLM:
    """Keyword/regex heuristics over our synthetic document format. Deterministic."""

    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        json_mode: bool = False,
    ) -> ChatResult:
        system = str(messages[0].get("content", ""))
        user = str(messages[-1].get("content", ""))
        doc = _between(r"<document>\n?([\s\S]*?)</document>", user) or user
        if "TASK: classify" in system:
            return ChatResult(content=json.dumps(self._classify(doc)), model="offline")
        if "TASK: extract" in system:
            return ChatResult(content=json.dumps(self._extract(doc)), model="offline")
        if "TASK: draft_borrower_message" in system:
            items = re.findall(r"^- (.+)$", user, re.M)
            body = (
                "Hi! To keep your loan moving, we still need:\n"
                + "\n".join(f"• {i}" for i in items)
                + "\nYou can send a photo or PDF right here. Thank you!"
            )
            return ChatResult(content=json.dumps({"message": body}), model="offline")
        return ChatResult(
            content="Offline mode: I can only run the document pipeline.", model="offline"
        )

    @staticmethod
    def _classify(doc: str) -> dict[str, Any]:
        d = doc.lower()
        if "earnings statement" in d or "pay date" in d:
            return {"doc_type": "paystub", "confidence": 0.95, "reason": "pay date/earnings"}
        if "form w-2" in d or "wage and tax statement" in d:
            return {"doc_type": "w2", "confidence": 0.95, "reason": "W-2 header"}
        if "statement period" in d and "balance" in d:
            return {"doc_type": "bank_statement", "confidence": 0.9, "reason": "balance/period"}
        return {"doc_type": "unknown", "confidence": 0.3, "reason": "no known markers"}

    @staticmethod
    def _extract(doc: str) -> dict[str, Any]:
        def g(label: str) -> str | None:
            return _between(rf"^{label}\s*:\s*(.+)$", doc)

        def money(label: str) -> str | None:
            v = g(label)
            return v.replace("$", "").replace(",", "") if v else None

        if g("Pay Date"):
            return {
                "employee_name": g("Employee"),
                "employer_name": g("Employer"),
                "pay_date": g("Pay Date"),
                "pay_frequency": (g("Pay Frequency") or "").lower(),
                "gross_pay": money("Gross Pay"),
                "net_pay": money("Net Pay"),
                "ytd_gross": money("YTD Gross"),
                "evidence": [{"field": "gross_pay", "snippet": f"Gross Pay: {g('Gross Pay')}"}],
            }
        if g("Tax Year"):
            return {
                "employee_name": g("Employee"),
                "employer_name": g("Employer"),
                "tax_year": int(g("Tax Year") or 0),
                "wages": money("Wages"),
                "evidence": [{"field": "wages", "snippet": f"Wages: {g('Wages')}"}],
            }
        if g("Statement End"):
            return {
                "account_holder": g("Account Holder"),
                "bank_name": g("Bank"),
                "statement_end_date": g("Statement End"),
                "ending_balance": money("Ending Balance"),
                "evidence": [],
            }
        raise LLMError("offline extractor: unrecognized layout")
