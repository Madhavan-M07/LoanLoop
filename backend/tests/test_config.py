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


DB = "postgresql+asyncpg://u:p@127.0.0.1:5432/db"  # secret-scan: allow (dummy)


def test_valid_prod_config_starts():
    s = make(env="prod", principals_json=PRINCIPALS, llm_providers_json=PROVIDERS, database_url=DB)
    assert list(s.principals()) == ["tok"]


def test_prod_refuses_to_start_without_a_database():
    """In prod, data must persist: an in-memory store would lose loan files on restart."""
    with pytest.raises(ValidationError, match="LOANLOOP_DATABASE_URL"):
        make(env="prod", principals_json=PRINCIPALS, llm_providers_json=PROVIDERS)


def test_dev_without_any_identities_refuses_to_guess():
    with pytest.raises(RuntimeError, match="no identities configured"):
        make(env="dev", llm_mode="offline").principals()


def test_thresholds_are_configurable_and_validated():
    s = make(env="dev", llm_mode="offline", classify_min_confidence=0.8, stuck_after_days=5)
    assert (s.classify_min_confidence, s.stuck_after_days) == (0.8, 5)
    with pytest.raises(ValidationError):
        make(env="dev", llm_mode="offline", classify_min_confidence=1.5)


def test_config_errors_never_echo_secret_values():
    """Regression: a refused config printed the tail of a real key from the developer's env
    file in its error message (pydantic includes input values by default)."""
    fake_db = "postgresql+asyncpg://u:SuperSecretPw987@127.0.0.1:5432/db"  # noqa: S105  # secret-scan: allow
    fake_token = "tg-SECRET-TOKEN-123"  # noqa: S105  (fake)
    with pytest.raises(ValidationError) as e:
        make(env="prod", database_url=fake_db, telegram_bot_token=fake_token)
    message = str(e.value)
    assert "SuperSecretPw987" not in message
    assert "tg-SECRET-TOKEN-123" not in message
    assert "LOANLOOP_PRINCIPALS_JSON" in message  # still says WHAT is wrong
