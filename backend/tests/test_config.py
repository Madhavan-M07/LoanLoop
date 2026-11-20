"""The app must fail SAFE: a missing or careless config refuses to start, never opens up."""

import json

import pytest
from pydantic import ValidationError

from app.core.config import Settings

PROVIDERS = json.dumps([{"name": "g", "base_url": "https://x/v1", "model": "m"}])
PRINCIPALS = json.dumps({"tok": {"subject": "s", "scope": "processor", "org_id": "o"}})


def make(**kw) -> Settings:
    base = {"principals_json": "", "llm_providers_json": "[]", "demo_data_path": ""}
    return Settings(_env_file=None, **{**base, **kw})  # hermetic: ignore real .env


def test_default_environment_is_prod_and_refuses_to_start_unconfigured(monkeypatch):
    for var in ("LOANLOOP_ENV", "LOANLOOP_LLM_MODE", "LOANLOOP_PRINCIPALS_JSON"):
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(ValidationError, match="PRINCIPALS_JSON must be set"):
        make()


def test_prod_rejects_offline_model():
    with pytest.raises(ValidationError, match="LLM_MODE must be 'providers'"):
        make(env="prod", llm_mode="offline", principals_json=PRINCIPALS)


def test_prod_rejects_demo_data():
    with pytest.raises(ValidationError, match="DEMO_DATA_PATH is not allowed"):
        make(
            env="prod",
            principals_json=PRINCIPALS,
            llm_providers_json=PROVIDERS,
            demo_data_path="demo.json",
        )


def test_providers_mode_requires_providers():
    with pytest.raises(ValidationError, match="PROVIDERS_JSON is empty"):
        make(env="dev", llm_mode="providers")


def test_valid_prod_config_starts():
    s = make(env="prod", principals_json=PRINCIPALS, llm_providers_json=PROVIDERS)
    assert list(s.principals()) == ["tok"]


def test_dev_without_any_identities_refuses_to_guess():
    with pytest.raises(RuntimeError, match="no identities configured"):
        make(env="dev", llm_mode="offline").principals()


def test_thresholds_are_configurable_and_validated():
    s = make(env="dev", llm_mode="offline", classify_min_confidence=0.8, stuck_after_days=5)
    assert (s.classify_min_confidence, s.stuck_after_days) == (0.8, 5)
    with pytest.raises(ValidationError):
        make(env="dev", llm_mode="offline", classify_min_confidence=1.5)
