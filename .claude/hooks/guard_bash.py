"""PreToolUse(Bash): block catastrophic commands, ask on risky ones."""

import re

from _common import decide, read_input

DENY = [
    (
        r"\brm\s+-\w*r\w*\s+(/|~|\*|\.\.?)(\s|$)",
        "Recursive delete of root/home/cwd/parent is never allowed.",
    ),
    (
        r"git\s+push\s+.*(--force\b|-f\b)",
        "Force push is not allowed. Use a new commit or --force-with-lease after asking.",
    ),
    (
        r"(curl|wget)[^|]*\|\s*(ba|z)?sh",
        "Piping a download into a shell is not allowed. Download, inspect, then run.",
    ),
    (
        r"(cat|type|less|more|head|tail|bat)\s+[^|;&]*\.env(\.(local|production))?(\s|$)",
        "Do not read .env files. Use .env.example for structure.",
    ),
    (r"\b(printenv|env)\s*$", "Do not dump environment variables (may contain secrets)."),
    (r"evals/data/real", "Real borrower data must never be touched by agents."),
]

ASK = [
    (r"git\s+push\s+\S+\s+(main|master)\b", "Pushing directly to main. Use a feature branch + PR."),
    (r"git\s+(reset\s+--hard|clean\s+-\w*f)", "Destroys uncommitted work."),
    (r"\bdrop\s+(database|table|schema)\b", "Destructive SQL."),
    (r"\btruncate\s+table\b", "Destructive SQL."),
    (
        r"docker\s+(compose\s+down\s+.*-v|volume\s+rm|system\s+prune)",
        "Deletes Docker volumes/data.",
    ),
    (r"\b(ssh|scp|rsync)\b.*@", "Touches a remote server."),
    (r"coolify|deploy", "Deployment is outward-facing."),
]

data = read_input()
cmd = (data.get("tool_input") or {}).get("command", "")
low = cmd.lower()

for pattern, reason in DENY:
    if re.search(pattern, low):
        decide("deny", f"LoanLoop guard: {reason}")

for pattern, reason in ASK:
    if re.search(pattern, low):
        decide("ask", f"LoanLoop guard: {reason}")
