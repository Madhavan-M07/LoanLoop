"""Heuristic prompt-injection detector for uploaded document text.

Detection is a tripwire, not the defense. The real defenses are structural: no tools for
document agents, schema-only output, and decisions made by the rules engine. A hit routes the
document to human review and is audit-logged.
"""

from __future__ import annotations

import re

_PATTERNS = [
    r"ignore (all |any )?(previous|prior|above) (instructions|prompts?)",
    r"disregard (the )?(system|previous) (prompt|instructions)",
    r"you are now\b",
    r"\bsystem prompt\b",
    r"(mark|set|flag) (this|the)? ?(income|file|loan|document)s? "
    r"(as )?(verified|approved|complete)",
    r"\bapprove (this|the) (loan|file)\b",
    r"\b(call|use|invoke) the \w+ tool\b",
    r"</?document>",
]
_RX = re.compile("|".join(f"(?:{p})" for p in _PATTERNS), re.I)


def detect_injection(text: str) -> list[str]:
    return sorted({m.group(0).lower() for m in _RX.finditer(text)})
