from __future__ import annotations

from datetime import UTC, datetime

import pytest
from app.core.config import Settings
from app.services.store import Store, seed_demo

FIXED_NOW = datetime(2026, 11, 20, 15, 0, tzinfo=UTC)


@pytest.fixture
def store() -> Store:
    return seed_demo(Store(clock=lambda: FIXED_NOW))


@pytest.fixture
def settings() -> Settings:
    return Settings(env="test", llm_mode="offline", principals_json="", telegram_bot_token="")
