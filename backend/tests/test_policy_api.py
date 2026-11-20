"""Lender policy is per-organization data: readable by processors, changeable only by human
admins, validated, audited, and applied to open files immediately."""

from datetime import timedelta

import pytest
from app.api.main import create_app
from app.llm.fake import OfflineLLM
from app.services import synthetic
from app.services.store import Store, load_loans
from fastapi.testclient import TestClient

from tests.conftest import FIXED_NOW

TOKENS = {
    "admin": "dev-processor-acme",  # is_admin in demo data
    "proc_beta": "dev-processor-beta",  # processor, not admin
    "hermes": "dev-hermes-acme",  # agent identity
    "borrower": "dev-borrower-priya",
}
H = {k: {"Authorization": f"Bearer {t}"} for k, t in TOKENS.items()}
ACME = {
    "paystub_max_age_days": 30,
    "bank_statement_max_age_days": 60,
    "w2_max_years_back": 2,
    "max_dti": "0.43",
}


@pytest.fixture
def client(store, settings):
    return TestClient(create_app(settings=settings, store=store, llm=OfflineLLM()))


def test_each_organization_reads_its_own_policy(client):
    assert client.get("/org/policy", headers=H["admin"]).json()["paystub_max_age_days"] == 30
    assert client.get("/org/policy", headers=H["proc_beta"]).json()["paystub_max_age_days"] == 45


def test_borrowers_cannot_read_policy(client):
    assert client.get("/org/policy", headers=H["borrower"]).status_code == 403


@pytest.mark.parametrize("who", ["proc_beta", "hermes", "borrower"])
def test_only_human_admins_can_change_policy(client, who):
    r = client.put("/org/policy", headers=H[who], json={**ACME, "paystub_max_age_days": 90})
    assert r.status_code == 403


@pytest.mark.parametrize(
    "bad",
    [
        {"paystub_max_age_days": 0},
        {"max_dti": "1.5"},
        {"unknown_field": 1},
    ],
)
def test_invalid_policy_is_rejected(client, bad):
    assert client.put("/org/policy", headers=H["admin"], json={**ACME, **bad}).status_code == 422


def test_missing_policy_field_is_rejected(client):
    partial = {k: v for k, v in ACME.items() if k != "max_dti"}
    assert client.put("/org/policy", headers=H["admin"], json=partial).status_code == 422


def test_policy_change_is_audited_with_before_and_after(client, store):
    client.put("/org/policy", headers=H["admin"], json={**ACME, "paystub_max_age_days": 45})
    events = [e for e in store.audit_log if e.action == "policy_updated"]
    assert len(events) == 1 and events[0].org_id == "acme"
    assert "paystub_max_age_days: 30 -> 45" in events[0].detail
    audit = client.get("/audit", headers=H["admin"]).json()
    assert any(e["action"] == "policy_updated" for e in audit)


def test_policy_change_rechecks_open_files_without_faking_activity(client, store):
    stub_date = (FIXED_NOW - timedelta(days=40)).date()  # 40 days: too old under 30-day policy
    client.post(
        "/loans/L-1001/documents",
        headers=H["borrower"],
        json={
            "filename": "stub.txt",
            "text": synthetic.paystub(
                employee="Priya Sharma", employer="Acme Robotics", pay_date=stub_date
            ),
        },
    )
    codes = {r.code for r in store.results["L-1001"]}
    assert "paystub_expired" in codes
    activity_before = store.loans["L-1001"].last_activity_at

    store.now = lambda: FIXED_NOW + timedelta(days=3)  # admin changes policy later
    r = client.put("/org/policy", headers=H["admin"], json={**ACME, "paystub_max_age_days": 60})
    assert r.status_code == 200

    assert "paystub_expired" not in {r.code for r in store.results["L-1001"]}
    assert store.loans["L-1001"].last_activity_at == activity_before  # not fake activity


def test_other_organizations_are_unaffected(client):
    client.put("/org/policy", headers=H["admin"], json={**ACME, "paystub_max_age_days": 90})
    assert client.get("/org/policy", headers=H["proc_beta"]).json()["paystub_max_age_days"] == 45


def test_loans_for_unknown_organizations_are_refused():
    with pytest.raises(LookupError, match="not configured"):
        load_loans(
            Store(),
            [
                {
                    "id": "X-1",
                    "org_id": "nope",
                    "borrower_name": "A",
                    "borrower_subject": "a",
                    "loan_officer": "lo",
                    "monthly_debts": "1",
                    "required_docs": ["paystub"],
                }
            ],
        )
