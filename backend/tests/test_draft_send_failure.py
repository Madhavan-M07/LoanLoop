"""A failed send must never leave a draft stuck where no one can see it.

Before the fix: approve -> notifier fails -> draft stays APPROVED, which is neither in the inbox
nor approvable again, so the borrower is silently never chased (hurts O4).
"""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.api.main import create_app
from app.domain.models import Loan
from app.llm.fake import OfflineLLM
from tests import synthetic
from tests.test_pipeline_api import H, full_file, upload


class FlakyNotifier:
    """Fails (or raises) until told to recover."""

    def __init__(self) -> None:
        self.mode = "fail"  # fail | raise | ok
        self.sent: list[str] = []

    async def send(self, loan: Loan, body: str) -> bool:
        if self.mode == "raise":
            raise RuntimeError("provider exploded")
        if self.mode == "fail":
            return False
        self.sent.append(body)
        return True


@pytest.fixture
def notifier() -> FlakyNotifier:
    return FlakyNotifier()


@pytest.fixture
def client(store, settings, notifier):
    return TestClient(
        create_app(settings=settings, store=store, llm=OfflineLLM(), notifier=notifier)
    )


def _approve_first_draft(client):
    draft_id = client.get("/drafts", headers=H["proc"]).json()[0]["id"]
    return draft_id, client.post(f"/drafts/{draft_id}/approve", headers=H["proc"])


@pytest.mark.parametrize("mode", ["fail", "raise"])
def test_failed_send_is_marked_and_stays_in_inbox(client, store, notifier, mode):
    notifier.mode = mode
    full_file(client, stub_date=date(2026, 9, 30))  # expired paystub -> draft
    draft_id, r = _approve_first_draft(client)

    assert r.status_code == 200 and r.json()["status"] == "send_failed"
    inbox = client.get("/drafts", headers=H["proc"]).json()
    assert [d["id"] for d in inbox] == [draft_id]  # still visible to the processor
    assert any(e.action == "message_send_failed" for e in store.audit_log)


def test_processor_can_retry_a_failed_send(client, notifier):
    full_file(client, stub_date=date(2026, 9, 30))
    draft_id, _ = _approve_first_draft(client)

    notifier.mode = "ok"
    r = client.post(f"/drafts/{draft_id}/approve", headers=H["proc"])
    assert r.status_code == 200 and r.json()["status"] == "sent"
    assert len(notifier.sent) == 1
    assert client.get("/drafts", headers=H["proc"]).json() == []
    # sent is final: no double send
    assert client.post(f"/drafts/{draft_id}/approve", headers=H["proc"]).status_code == 403


def test_agents_cannot_retry_a_failed_send(client):
    full_file(client, stub_date=date(2026, 9, 30))
    draft_id, _ = _approve_first_draft(client)
    assert client.post(f"/drafts/{draft_id}/approve", headers=H["hermes"]).status_code == 403


def test_processor_can_drop_a_failed_send(client):
    full_file(client, stub_date=date(2026, 9, 30))
    draft_id, _ = _approve_first_draft(client)
    r = client.post(f"/drafts/{draft_id}/reject", headers=H["proc"])
    assert r.status_code == 200 and r.json()["status"] == "rejected"
    assert client.get("/drafts", headers=H["proc"]).json() == []


def test_failed_draft_is_retired_when_no_longer_needed(client, store):
    # Paystub + W-2 only: the draft asks for the missing bank statement
    upload(
        client,
        "priya",
        "L-1001",
        "stub.txt",
        synthetic.paystub(
            employee="Priya Sharma", employer="Acme Robotics Inc.", pay_date=date(2026, 11, 14)
        ),
    )
    upload(
        client,
        "priya",
        "L-1001",
        "w2.txt",
        synthetic.w2(employee="Priya Sharma", employer="Acme Robotics LLC", tax_year=2025),
    )
    draft_id, _ = _approve_first_draft(client)

    # Borrower sends it anyway: nothing outstanding, so the failed request is stale
    upload(
        client,
        "priya",
        "L-1001",
        "bank.txt",
        synthetic.bank_statement(
            holder="Priya Sharma", bank="First Demo Bank", end=date(2026, 10, 31)
        ),
    )
    assert store.loans["L-1001"].stage == "file_complete"
    assert store.drafts[draft_id].status == "rejected"
    assert client.get("/drafts", headers=H["proc"]).json() == []
