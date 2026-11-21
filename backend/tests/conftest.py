from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.core.config import Settings
from app.data.store import Store, load_loans, load_orgs

FIXED_NOW = datetime(2026, 11, 20, 15, 0, tzinfo=UTC)
DEMO_DATA = Path(__file__).resolve().parents[1] / "demo" / "demo_data.json"
PG_URL = os.environ.get("LOANLOOP_TEST_DATABASE_URL", "")


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


@pytest.fixture(scope="session")
def pg_template() -> Iterator[str]:
    """Migrated + demo-seeded template database, built once per test run."""
    from tests import pg_support

    demo = Settings(
        _env_file=None, env="test", llm_mode="offline", demo_data_path=str(DEMO_DATA)
    ).demo_data()
    assert demo is not None
    name = pg_support.make_template(PG_URL, demo, FIXED_NOW)
    try:
        yield name
    finally:
        pg_support.drop(PG_URL, name)


# Every test that uses `store` runs twice: in memory, and against a real Postgres database
# (when LOANLOOP_TEST_DATABASE_URL is set). Same tests, same assertions, both backends.
@pytest.fixture(
    params=[
        "memory",
        pytest.param(
            "postgres",
            marks=pytest.mark.skipif(not PG_URL, reason="set LOANLOOP_TEST_DATABASE_URL"),
        ),
    ]
)
def store(request: pytest.FixtureRequest, settings: Settings) -> Iterator[object]:
    if request.param == "memory":
        demo = settings.demo_data()
        assert demo is not None
        s = load_orgs(Store(clock=lambda: FIXED_NOW), demo["organizations"])
        yield load_loans(s, demo["loans"])
        return

    from tests import pg_support

    template = request.getfixturevalue("pg_template")
    name = pg_support.clone(PG_URL, template)
    try:
        yield pg_support.PgTestStore(pg_support.with_db(PG_URL, name), lambda: FIXED_NOW)
    finally:
        pg_support.drop(PG_URL, name)
