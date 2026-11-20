"""End-to-end through the HTTP API with the offline model: upload -> agents -> rules -> draft
-> human approval. Plus the security properties that matter most."""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.api.main import create_app
from app.domain.models import DocStatus
from app.llm.fake import OfflineLLM
from tests import synthetic

H = {
    k: {"Authorization": f"Bearer {t}"}
    for k, t in {
        "proc": "dev-processor-acme",
        "proc_beta": "dev-processor-beta",
        "priya": "dev-borrower-priya",
        "john": "dev-borrower-john",
        "hermes": "dev-hermes-acme",
        "openclaw": "dev-openclaw-priya",
    }.items()
}


@pytest.fixture
def client(store, settings):
    return TestClient(create_app(settings=settings, store=store, llm=OfflineLLM()))


def upload(client, who, loan_id, filename, text):
    return client.post(
        f"/loans/{loan_id}/documents", headers=H[who], json={"filename": filename, "text": text}
    )


def full_file(client, who="priya", stub_date=date(2026, 11, 14)):
    upload(
        client,
        who,
        "L-1001",
        "stub.txt",
        synthetic.paystub(
            employee="Priya Sharma", employer="Acme Robotics Inc.", pay_date=stub_date
        ),
    )
    upload(
        client,
        who,
        "L-1001",
        "w2.txt",
        synthetic.w2(employee="Priya Sharma", employer="Acme Robotics LLC", tax_year=2025),
    )
    return upload(
        client,
        who,
        "L-1001",
        "bank.txt",
        synthetic.bank_statement(
            holder="Priya Sharma", bank="First Demo Bank", end=date(2026, 10, 31)
        ),
    )


def test_auth_required(client):
    assert client.get("/loans").status_code == 401
    assert client.get("/loans", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_complete_file_reaches_file_complete(client, store):
    r = full_file(client)
    assert r.status_code == 201 and r.json()["status"] == "extracted"
    assert store.loans["L-1001"].stage == "file_complete"
    assert client.get("/drafts", headers=H["proc"]).json() == []


def test_expired_paystub_creates_condition_and_draft_awaiting_human(client, store):
    full_file(client, stub_date=date(2026, 9, 30))
    status = client.get("/loans/L-1001/status", headers=H["priya"]).json()
    assert status["stage"] == "collecting_documents"
    assert any("paystub" in i for i in status["outstanding_items"])
    drafts = client.get("/drafts", headers=H["proc"]).json()
    assert len(drafts) == 1 and drafts[0]["status"] == "pending_approval"
    assert store.outbox == []  # nothing sent without approval


def test_human_approval_sends_message(client, store):
    full_file(client, stub_date=date(2026, 9, 30))
    draft_id = client.get("/drafts", headers=H["proc"]).json()[0]["id"]
    r = client.post(f"/drafts/{draft_id}/approve", headers=H["proc"])
    assert r.status_code == 200 and r.json()["status"] == "sent"
    assert len(store.outbox) == 1
    assert (
        client.post(f"/drafts/{draft_id}/approve", headers=H["proc"]).status_code == 403
    )  # no double send


def test_agents_can_draft_but_never_approve(client):
    r = client.post(
        "/drafts",
        headers=H["hermes"],
        json={"loan_id": "L-1002", "body": "Hi John, please send your W-2."},
    )
    assert r.status_code == 201
    assert client.post(f"/drafts/{r.json()['id']}/approve", headers=H["hermes"]).status_code == 403
    assert client.post(f"/drafts/{r.json()['id']}/approve", headers=H["proc"]).status_code == 200


def test_borrower_cannot_see_other_loans(client):
    assert client.get("/loans/L-1002/status", headers=H["priya"]).status_code == 404
    assert upload(client, "priya", "L-1002", "x.txt", "Pay Date: 2026-11-01").status_code == 404
    assert [ln["loan_id"] for ln in client.get("/loans", headers=H["priya"]).json()] == ["L-1001"]


def test_borrower_cannot_use_processor_endpoints(client):
    assert client.get("/loans/L-1001", headers=H["priya"]).status_code == 403
    assert client.get("/drafts", headers=H["priya"]).status_code == 403


def test_processor_cannot_cross_tenants(client):
    assert client.get("/loans/L-1001", headers=H["proc_beta"]).status_code == 404
    assert [ln["loan_id"] for ln in client.get("/loans", headers=H["proc_beta"]).json()] == [
        "L-2001"
    ]


def test_prompt_injection_document_goes_to_human_review(client, store):
    text = synthetic.paystub(
        employee="Priya Sharma",
        employer="Acme Robotics Inc.",
        pay_date=date(2026, 9, 1),
        extra=synthetic.INJECTION_FOOTER,
    )
    doc = upload(client, "priya", "L-1001", "stub.txt", text).json()
    assert doc["status"] == DocStatus.NEEDS_REVIEW
    assert any("injection" in r for r in doc["review_reasons"])
    assert store.loans["L-1001"].stage != "file_complete"
    assert any(e.action == "injection_suspected" for e in store.audit_log)


def test_pii_never_appears_in_audit_log(client, store):
    full_file(client)
    blob = " ".join(e.detail for e in store.audit_log)
    assert "123-45-6789" not in blob and "4455667788" not in blob


def test_unknown_document_needs_review(client):
    doc = upload(client, "priya", "L-1001", "selfie.txt", "a photo of a cat").json()
    assert doc["status"] == "needs_review"


def test_agent_uploads_do_not_return_extracted_fields(client):
    doc = upload(
        client,
        "openclaw",
        "L-1001",
        "stub.txt",
        synthetic.paystub(employee="Priya Sharma", employer="Acme", pay_date=date(2026, 11, 14)),
    ).json()
    assert doc["status"] == "extracted" and doc["fields"] is None


def test_stuck_files(client):
    stuck = client.get("/loans/stuck", headers=H["proc"]).json()
    assert [s["loan_id"] for s in stuck] == ["L-1002"]  # 4 days idle; L-1001 is fresh
