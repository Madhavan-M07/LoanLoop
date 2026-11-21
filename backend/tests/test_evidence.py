"""Evidence snippets (raw document text behind each extracted value) reach human processors,
and never agents or the assistant, whose output can go to an outside LLM provider."""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.api.main import create_app
from app.domain.models import Principal, Scope
from app.llm.fake import OfflineLLM
from app.services import loans
from tests import synthetic
from tests.test_pipeline_api import H, upload

STUB = synthetic.paystub(
    employee="Priya Sharma", employer="Acme Robotics Inc.", pay_date=date(2026, 11, 14)
)


@pytest.fixture
def client(store, settings):
    c = TestClient(create_app(settings=settings, store=store, llm=OfflineLLM()))
    assert upload(c, "priya", "L-1001", "stub.txt", STUB).status_code == 201
    return c


def _evidence(file: dict) -> list:
    return [e for d in file["documents"] if d["fields"] for e in d["fields"].get("evidence", [])]


def test_human_processor_sees_source_evidence_for_extracted_values(client):
    file = client.get("/loans/L-1001", headers=H["proc"]).json()
    evidence = _evidence(file)
    assert evidence and evidence[0]["field"] == "gross_pay"
    assert "Gross Pay" in evidence[0]["snippet"]


def test_agent_identity_never_receives_evidence(client):
    file = client.get("/loans/L-1001", headers=H["hermes"]).json()
    assert file["documents"] and _evidence(file) == []


async def test_assistant_path_never_includes_evidence(client, store):
    """The assistant's get_loan_file tool calls loans.loan_file without include_evidence."""
    human = Principal(subject="proc-anita", scope=Scope.PROCESSOR, org_id="acme")
    file = await loans.loan_file(store, human, "L-1001")
    assert file.documents and all(not d.fields or not d.fields.evidence for d in file.documents)
