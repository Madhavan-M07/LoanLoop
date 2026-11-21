"""Step 3c: the app on PostgreSQL. Data survives a restart; audit rows record before -> after;
the demo loader is safe to re-run.

Postgres-only tests run when LOANLOOP_TEST_DATABASE_URL is set.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.api.main import create_app
from app.core.config import Settings
from app.data.seed import load_demo
from app.domain.models import LoanStage
from app.llm.fake import OfflineLLM
from tests import synthetic
from tests.conftest import DEMO_DATA, FIXED_NOW, PG_URL
from tests.test_pipeline_api import H, upload

needs_pg = pytest.mark.skipif(not PG_URL, reason="set LOANLOOP_TEST_DATABASE_URL")


@pytest.fixture
def db_url(pg_template: str) -> Iterator[str]:
    from tests import pg_support

    name = pg_support.clone(PG_URL, pg_template)
    try:
        yield pg_support.with_db(PG_URL, name)
    finally:
        pg_support.drop(PG_URL, name)


def _pg_settings(url: str) -> Settings:
    return Settings(
        _env_file=None,
        env="test",
        llm_mode="offline",
        demo_data_path=str(DEMO_DATA),  # identities only: loans come from the database
        database_url=url,
    )


def _start(url: str) -> TestClient:
    """A brand-new app process as far as storage is concerned: nothing kept in memory."""
    return TestClient(create_app(settings=_pg_settings(url), llm=OfflineLLM()))


@needs_pg
def test_loan_file_survives_an_app_restart(db_url):
    stub = synthetic.paystub(
        employee="Priya Sharma", employer="Acme Robotics Inc.", pay_date=date(2026, 11, 14)
    )
    with _start(db_url) as first:
        assert first.get("/health").json()["database"] == "ok"
        r = upload(first, "priya", "L-1001", "stub.txt", stub)
        assert r.status_code == 201
        doc_id = r.json()["id"]
        drafts_before = first.get("/drafts", headers=H["proc"]).json()

    with _start(db_url) as second:  # the first app is gone; only the database remains
        file = second.get("/loans/L-1001", headers=H["proc"]).json()
        assert [d["id"] for d in file["documents"]] == [doc_id]
        assert file["documents"][0]["status"] == "extracted"
        assert second.get("/drafts", headers=H["proc"]).json() == drafts_before
        actions = {e["action"] for e in second.get("/audit", headers=H["proc"]).json()}
        assert {"document_uploaded", "classified", "extracted", "evaluated"} <= actions


@needs_pg
def test_app_uses_postgres_not_memory_when_database_is_configured(db_url):
    with _start(db_url) as client:
        loans = client.get("/loans", headers=H["proc"]).json()
    assert {ln["loan_id"] for ln in loans} >= {"L-1001"}  # came from the seeded database


def test_stage_change_is_audited_with_before_and_after(store, settings):
    """Runs on both backends (memory and Postgres)."""
    client = TestClient(create_app(settings=settings, store=store, llm=OfflineLLM()))
    stub = synthetic.paystub(
        employee="Priya Sharma", employer="Acme Robotics Inc.", pay_date=date(2026, 11, 14)
    )
    upload(client, "priya", "L-1001", "stub.txt", stub)
    events = client.get("/audit", params={"loan_id": "L-1001"}, headers=H["proc"]).json()
    evaluated = [e for e in events if e["action"] == "evaluated"]
    assert evaluated, events
    assert evaluated[-1]["before"]["stage"] == "collecting_documents"
    assert set(evaluated[-1]["after"]) == {"stage"}


def test_draft_decision_is_audited_with_before_and_after(store, settings):
    client = TestClient(create_app(settings=settings, store=store, llm=OfflineLLM()))
    stub = synthetic.paystub(
        employee="Priya Sharma", employer="Acme Robotics Inc.", pay_date=date(2026, 11, 14)
    )
    upload(client, "priya", "L-1001", "stub.txt", stub)
    draft_id = client.get("/drafts", headers=H["proc"]).json()[0]["id"]
    assert client.post(f"/drafts/{draft_id}/reject", headers=H["proc"]).status_code == 200
    events = client.get("/audit", params={"loan_id": "L-1001"}, headers=H["proc"]).json()
    rejected = next(e for e in events if e["action"] == "draft_rejected")
    assert rejected["before"] == {"status": "pending_approval"}
    assert rejected["after"] == {"status": "rejected"}


@needs_pg
def test_demo_loader_is_safe_to_rerun_and_never_undoes_progress(db_url):
    from tests import pg_support

    repo = pg_support.PgTestStore(db_url, lambda: FIXED_NOW)
    demo = _pg_settings(db_url).demo_data()
    assert demo is not None

    async def scenario() -> tuple[tuple[int, int], str]:
        async with repo.session() as s:  # real progress on a loan
            loan = await s.get_loan("L-1001")
            assert loan is not None
            loan.stage = LoanStage.COMPLETE
            await s.save_loan(loan)
        added = await load_demo(repo, demo)  # template already holds the demo data
        async with repo.session() as s:
            after = await s.get_loan("L-1001")
        assert after is not None
        return added, after.stage.value

    added, stage = asyncio.run(scenario())
    assert added == (0, 0)
    assert stage == "file_complete"  # not reset to the demo's starting stage
