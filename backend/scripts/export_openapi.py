"""Write the API's OpenAPI schema to frontend/openapi.json (the frontend's types are generated
from it with `npm run gen:api`). Deterministic output, so a stale schema shows up as a git diff.

Run from backend/:  uv run python scripts/export_openapi.py [--check]
--check exits 1 if the committed schema differs from the code (used by CI).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.api.main import create_app  # noqa: E402
from app.core.config import Settings  # noqa: E402
from app.llm.fake import OfflineLLM  # noqa: E402

TARGET = BACKEND.parent / "frontend" / "openapi.json"


def render() -> str:
    settings = Settings(
        _env_file=None,
        env="test",
        llm_mode="offline",
        demo_data_path=str(BACKEND / "demo" / "demo_data.json"),
    )
    schema = create_app(settings=settings, llm=OfflineLLM()).openapi()
    return json.dumps(schema, indent=2, sort_keys=True) + "\n"


def main() -> int:
    text = render()
    if "--check" in sys.argv:
        if not TARGET.exists() or TARGET.read_text(encoding="utf-8") != text:
            print(
                "frontend/openapi.json is out of date. Run: "
                "uv run python scripts/export_openapi.py && (cd ../frontend && npm run gen:api)"
            )
            return 1
        print("frontend/openapi.json is up to date.")
        return 0
    TARGET.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {TARGET.relative_to(BACKEND.parent)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
