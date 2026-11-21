"""Database connection: health reporting, failure handling, and that the password never leaks.

The `real Postgres` test runs only when LOANLOOP_TEST_DATABASE_URL points at a database
(local: `docker compose -f infra/docker-compose.yml up -d`; CI: a Postgres service).
"""

import os
import time

import pytest
from fastapi.testclient import TestClient

from app.api.main import create_app
from app.core.config import Settings
from app.data.db import Database
from app.llm.fake import OfflineLLM

PASSWORD = "not-a-real-pw-123"  # noqa: S105  # secret-scan: allow  (fake; checks masking)
# Nothing listens on port 1, so the connection is refused immediately.
UNREACHABLE = f"postgresql+asyncpg://loanloop:{PASSWORD}@127.0.0.1:1/loanloop"
REAL_DB = os.environ.get("LOANLOOP_TEST_DATABASE_URL", "")


def _settings(base: Settings, url: str | None) -> Settings:
    return Settings(
        **{**base.model_dump(exclude={"database_url"}), "database_url": url},
        _env_file=None,
    )


def _health(settings: Settings, store) -> TestClient:
    return TestClient(create_app(settings=settings, store=store, llm=OfflineLLM()))


def test_health_reports_database_not_configured_when_url_unset(settings, store):
    r = _health(settings, store).get("/health")
    assert r.status_code == 200
    assert r.json()["database"] == "not_configured"


def test_unreachable_database_reports_unavailable_quickly_without_leaking_password(settings, store):
    s = _settings(settings, UNREACHABLE)
    with _health(s, store) as client:  # `with` runs startup/shutdown (engine dispose)
        start = time.monotonic()
        r = client.get("/health")
        elapsed = time.monotonic() - start
    assert r.status_code == 200  # the API stays up; health reports the problem
    assert r.json()["database"] == "unavailable"
    assert PASSWORD not in r.text
    assert elapsed < s.database_timeout_s + 2


def test_database_url_is_secret_in_settings_repr(settings):
    s = _settings(settings, UNREACHABLE)
    assert PASSWORD not in repr(s)
    assert PASSWORD not in str(s.model_dump())


def test_wrong_driver_is_rejected_without_echoing_the_url():
    url = f"postgresql://loanloop:{PASSWORD}@localhost/loanloop"
    with pytest.raises(ValueError) as e:
        Database(url, timeout_s=1)
    assert PASSWORD not in str(e.value)


async def test_ping_times_out_instead_of_hanging():
    db = Database(UNREACHABLE, timeout_s=0.5)
    try:
        assert await db.ping() == "unavailable"
    finally:
        await db.dispose()


@pytest.mark.skipif(not REAL_DB, reason="set LOANLOOP_TEST_DATABASE_URL to run against Postgres")
async def test_ping_real_postgres_is_ok():
    db = Database(REAL_DB, timeout_s=5)
    try:
        assert await db.ping() == "ok"
    finally:
        await db.dispose()
