"""All configuration from environment variables (documented in backend/.env.example).

Fail-safe by design: the default environment is `prod`, and prod refuses to start unless real
identities and a real LLM provider are configured. Demo data loads ONLY from an explicit file
path in dev/test. No people, organizations, tokens or loans live in code.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.domain.models import Principal


class ProviderConfig(BaseModel):
    name: str
    base_url: str
    model: str
    api_key_env: str | None = None  # name of the env var holding the key (None for local Ollama)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LOANLOOP_", env_file=".env", extra="ignore")

    env: Literal["dev", "test", "prod"] = "prod"

    # LLM. "offline" = deterministic heuristic (no network), allowed only in dev/test.
    llm_mode: Literal["offline", "providers"] = "providers"
    llm_providers_json: str = "[]"  # JSON list of ProviderConfig, tried in order (fallback chain)
    llm_timeout_s: float = Field(30.0, gt=0)

    # Identities: JSON {"<token>": {principal...}}. Agents get their own principals with
    # via_agent set, so human-only actions can be refused to any agent identity.
    principals_json: str = ""

    # Dev/test only: JSON file with demo principals and loans (see backend/demo/).
    demo_data_path: str = ""

    # Outbound messages
    telegram_bot_token: str = ""
    notifier_timeout_s: float = Field(10.0, gt=0)

    # Pipeline / agent tuning (operational knobs, not lender policy)
    classify_min_confidence: float = Field(0.6, ge=0, le=1)
    max_document_chars: int = Field(50_000, gt=0)
    agent_max_steps: int = Field(5, ge=1, le=20)
    stuck_after_days: int = Field(2, ge=1)

    @property
    def providers(self) -> list[ProviderConfig]:
        return [ProviderConfig(**p) for p in json.loads(self.llm_providers_json or "[]")]

    @model_validator(mode="after")
    def _fail_safe(self) -> Self:
        problems: list[str] = []
        if self.env == "prod":
            if self.demo_data_path:
                problems.append("LOANLOOP_DEMO_DATA_PATH is not allowed in prod")
            if self.llm_mode != "providers":
                problems.append("LOANLOOP_LLM_MODE must be 'providers' in prod")
            if not self.principals_json:
                problems.append("LOANLOOP_PRINCIPALS_JSON must be set in prod")
        if self.llm_mode == "providers" and not self.providers:
            problems.append("LOANLOOP_LLM_PROVIDERS_JSON is empty but LLM_MODE=providers")
        if problems:
            raise ValueError("unsafe configuration: " + "; ".join(problems))
        return self

    def demo_data(self) -> dict | None:
        if not self.demo_data_path:
            return None
        return json.loads(Path(self.demo_data_path).read_text(encoding="utf-8"))

    def principals(self) -> dict[str, Principal]:
        if self.principals_json:
            raw = json.loads(self.principals_json)
        elif (demo := self.demo_data()) is not None:
            raw = demo.get("principals", {})
        else:
            raise RuntimeError("no identities configured: set LOANLOOP_PRINCIPALS_JSON")
        return {tok: Principal(**p) for tok, p in raw.items()}


@lru_cache
def get_settings() -> Settings:
    return Settings()
