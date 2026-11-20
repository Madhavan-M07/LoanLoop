"""All configuration from environment variables (see .env.example). No os.getenv elsewhere."""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Literal

from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.domain.models import Principal, Scope


class ProviderConfig(BaseModel):
    name: str
    base_url: str
    model: str
    api_key_env: str | None = None  # name of the env var holding the key (None for local Ollama)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LOANLOOP_", env_file=".env", extra="ignore")

    env: Literal["dev", "test", "prod"] = "dev"

    # LLM: "offline" = deterministic heuristic model (no network); "providers" = real models
    llm_mode: Literal["offline", "providers"] = "offline"
    llm_providers_json: str = "[]"  # JSON list of ProviderConfig, tried in order (fallback chain)
    llm_timeout_s: float = 30.0

    # Auth: JSON {"<token>": {principal...}}. In dev, demo tokens are used if unset.
    # Agents get their OWN principals with via_agent set (e.g. Hermes = processor scope,
    # via_agent="hermes"), so the API can refuse human-only actions to any agent identity.
    principals_json: str = ""

    telegram_bot_token: str = ""  # optional: send approved messages to borrowers

    @property
    def providers(self) -> list[ProviderConfig]:
        return [ProviderConfig(**p) for p in json.loads(self.llm_providers_json or "[]")]

    def principals(self) -> dict[str, Principal]:
        if self.principals_json:
            raw = json.loads(self.principals_json)
            return {tok: Principal(**p) for tok, p in raw.items()}
        if self.env == "prod":
            raise RuntimeError("LOANLOOP_PRINCIPALS_JSON must be set in prod")
        return DEMO_PRINCIPALS


# Demo identities for local dev/tests only (synthetic org + loans). Refused in prod.
DEMO_PRINCIPALS: dict[str, Principal] = {
    "dev-processor-acme": Principal(subject="proc-anita", scope=Scope.PROCESSOR, org_id="acme"),
    "dev-processor-beta": Principal(subject="proc-ravi", scope=Scope.PROCESSOR, org_id="beta"),
    "dev-borrower-priya": Principal(
        subject="bor-priya", scope=Scope.BORROWER, org_id="acme", loan_id="L-1001"
    ),
    "dev-borrower-john": Principal(
        subject="bor-john", scope=Scope.BORROWER, org_id="acme", loan_id="L-1002"
    ),
    # Agent identities (used by MCP clients). Production: OpenClaw per-requester OAuth maps each
    # chat user to their own borrower principal instead of one static token.
    "dev-hermes-acme": Principal(
        subject="hermes@acme", scope=Scope.PROCESSOR, org_id="acme", via_agent="hermes"
    ),
    "dev-openclaw-priya": Principal(
        subject="openclaw:bor-priya",
        scope=Scope.BORROWER,
        org_id="acme",
        loan_id="L-1001",
        via_agent="openclaw",
    ),
}


@lru_cache
def get_settings() -> Settings:
    return Settings()
