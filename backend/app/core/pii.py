"""PII detection and tokenization.

Sensitive identifiers are replaced with tokens (<SSN_1>, <ACCT_1>...) before any text leaves
our server for an external LLM. Real values stay in a per-document vault and are swapped back
locally only where needed.

Current detectors are pattern-based. Known limitation: personal NAMES and street addresses
are not detected yet (needs NER, planned: Microsoft Presidio). Documented in docs/SECURITY.md.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


def _aba_checksum_ok(digits: str) -> bool:
    if len(digits) != 9 or not digits.isdigit():
        return False
    d = [int(c) for c in digits]
    total = 3 * (d[0] + d[3] + d[6]) + 7 * (d[1] + d[4] + d[7]) + (d[2] + d[5] + d[8])
    return total % 10 == 0


# Order matters: more specific patterns first.
_DETECTORS: list[tuple[str, re.Pattern[str]]] = [
    ("SSN", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("EMAIL", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")),
    ("PHONE", re.compile(r"(?<!\d)(?:\+1[\s.-]?)?\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}(?!\d)")),
    (
        "DOB",
        re.compile(
            r"(?i)\b(?:dob|date of birth|birth ?date)\s*[:#]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})"
        ),
    ),
    (
        "ACCT",
        re.compile(r"(?i)\b(?:acct|account)(?:\s*(?:no|number|#))?\.?\s*[:#]?\s*([\dXx*-]{6,20})"),
    ),
    (
        "ROUTING",
        re.compile(r"(?i)\b(?:routing|aba|rtn)(?:\s*(?:no|number|#))?\.?\s*[:#]?\s*(\d{9})\b"),
    ),
]


@dataclass
class PiiVault:
    """Token -> real value for ONE document. Never logged, never sent to an LLM."""

    values: dict[str, str] = field(default_factory=dict)

    def rehydrate(self, obj: Any) -> Any:
        if isinstance(obj, str):
            for token, real in self.values.items():
                obj = obj.replace(token, real)
            return obj
        if isinstance(obj, dict):
            return {k: self.rehydrate(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self.rehydrate(v) for v in obj]
        return obj

    @property
    def kinds(self) -> list[str]:
        return sorted({t.strip("<>").rsplit("_", 1)[0] for t in self.values})


def tokenize(text: str) -> tuple[str, PiiVault]:
    """Replace PII with stable tokens. Same value -> same token within a document."""
    vault = PiiVault()
    reverse: dict[str, str] = {}
    counters: dict[str, int] = {}

    def token_for(kind: str, value: str) -> str:
        if value in reverse:
            return reverse[value]
        counters[kind] = counters.get(kind, 0) + 1
        tok = f"<{kind}_{counters[kind]}>"
        reverse[value] = tok
        vault.values[tok] = value
        return tok

    for kind, pattern in _DETECTORS:

        def repl(m: re.Match[str], kind: str = kind) -> str:
            if m.groups():  # labelled pattern: only replace the captured value
                value = m.group(1)
                if kind == "ROUTING" and not _aba_checksum_ok(value):
                    return m.group(0)
                start, end = m.span(1)
                s0 = m.start(0)
                full = m.group(0)
                return full[: start - s0] + token_for(kind, value) + full[end - s0 :]
            return token_for(kind, m.group(0))

        text = pattern.sub(repl, text)
    return text, vault


def mask_for_log(text: str) -> str:
    """Irreversible masking for logs, traces and error messages."""
    masked, vault = tokenize(text)
    for tok in vault.values:
        masked = masked.replace(tok, f"[{tok.strip('<>').rsplit('_', 1)[0]}]")
    return masked
