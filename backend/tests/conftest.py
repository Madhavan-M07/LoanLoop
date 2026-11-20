from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.core.config import Settings
from app.data.store import Store, load_loans, load_orgs

FIXED_NOW = datetime(2026, 11, 20, 15, 0, tzinfo=UTC)
DEMO_DATA = Path(__file__).resolve().parents[1] / "demo" / "demo_data.json"


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None,  # hermetic: never read the developer's real .env
        env="test",
        llm_mode="offline",
        principals_json="",
        demo_data_path=str(DEMO_DATA),
        telegram_bot_token="",
    )


@pytest.fixture
def store(settings: Settings) -> Store:
    demo = settings.demo_data()
    assert demo is not None
    store = load_orgs(Store(clock=lambda: FIXED_NOW), demo["organizations"])
    return load_loans(store, demo["loans"])
