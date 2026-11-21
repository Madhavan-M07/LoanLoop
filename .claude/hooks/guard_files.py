"""PreToolUse(Edit|Write|MultiEdit): protect secrets, real data, and generated files."""

import os
import re

from _common import decide, read_input, rel

data = read_input()
path = rel((data.get("tool_input") or {}).get("file_path", ""))
name = os.path.basename(path)

if re.fullmatch(r"\.env(\..+)?", name) and name != ".env.example":
    decide(
        "deny", "LoanLoop guard: never write .env files. Document new vars in .env.example instead."
    )

if re.search(r"\.(pem|key|p12|pfx)$", name):
    decide("deny", "LoanLoop guard: never write key/certificate files.")

if path.startswith("evals/data/real") or "/evals/data/real/" in "/" + path.replace("\\", "/"):
    decide(
        "deny",
        "LoanLoop guard: real borrower data is off-limits. "
        "Use synthetic data in evals/data/synthetic.",
    )

if name in {"uv.lock", "package-lock.json", "pnpm-lock.yaml"}:
    decide(
        "deny",
        "LoanLoop guard: lock files are generated. Run uv sync / npm install instead of editing.",
    )

if (
    re.search(r"/migrations/versions/.+\.py$|alembic/versions/.+\.py$", path)
    and data.get("tool_name") == "Edit"
):
    decide(
        "ask",
        "LoanLoop guard: editing an existing migration. "
        "Prefer a new migration if this one may already be applied.",
    )
