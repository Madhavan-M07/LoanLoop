"""Domain schemas. Every boundary (API, LLM output, MCP tool I/O) uses these Pydantic models."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Scope(StrEnum):
    BORROWER = "borrower"
    PROCESSOR = "processor"


class Principal(BaseModel):
    """Who is calling. Always derived from authentication, never from tool/LLM arguments."""

    subject: str
    scope: Scope
    org_id: str
    loan_id: str | None = None  # set for borrowers: the only loan they may touch
    via_agent: str | None = None  # e.g. "openclaw", "hermes" when acting through MCP
    is_admin: bool = False  # may change organization settings (humans only)


class LenderPolicy(BaseModel):
    """An organization's document rules. Required on every organization; there is no default
    in code. Bounds reject values that are clearly a mistake."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    paystub_max_age_days: int = Field(ge=1, le=365)
    bank_statement_max_age_days: int = Field(ge=1, le=365)
    w2_max_years_back: int = Field(ge=0, le=5, description="Oldest acceptable W-2: year - N")
    max_dti: Decimal = Field(gt=0, le=1, decimal_places=3)


class Organization(BaseModel):
    id: str
    name: str
    policy: LenderPolicy


class DocType(StrEnum):
    PAYSTUB = "paystub"
    W2 = "w2"
    BANK_STATEMENT = "bank_statement"
    UNKNOWN = "unknown"


class DocStatus(StrEnum):
    RECEIVED = "received"
    EXTRACTED = "extracted"
    NEEDS_REVIEW = "needs_review"
    REJECTED = "rejected"


class Evidence(BaseModel):
    field: str
    snippet: str = Field(max_length=300)


class Classification(BaseModel):
    doc_type: DocType
    confidence: float = Field(ge=0, le=1)
    reason: str = Field(max_length=300)


PayFrequency = Literal["weekly", "biweekly", "semimonthly", "monthly"]


class PaystubFields(BaseModel):
    employee_name: str
    employer_name: str
    pay_date: date
    pay_frequency: PayFrequency
    gross_pay: Decimal
    net_pay: Decimal
    ytd_gross: Decimal | None = None
    evidence: list[Evidence] = []


class W2Fields(BaseModel):
    employee_name: str
    employer_name: str
    tax_year: int
    wages: Decimal
    evidence: list[Evidence] = []


class BankStatementFields(BaseModel):
    account_holder: str
    bank_name: str
    statement_end_date: date
    ending_balance: Decimal
    evidence: list[Evidence] = []


ExtractedFields = PaystubFields | W2Fields | BankStatementFields

SCHEMA_FOR: dict[DocType, type[BaseModel]] = {
    DocType.PAYSTUB: PaystubFields,
    DocType.W2: W2Fields,
    DocType.BANK_STATEMENT: BankStatementFields,
}


class Document(BaseModel):
    id: str
    loan_id: str
    filename: str
    status: DocStatus
    doc_type: DocType = DocType.UNKNOWN
    classification: Classification | None = None
    fields: PaystubFields | W2Fields | BankStatementFields | None = None
    review_reasons: list[str] = []
    uploaded_by: str
    uploaded_at: datetime


class Severity(StrEnum):
    PASS = "pass"  # noqa: S105 (rule outcome, not a password)
    WARN = "warn"
    FAIL = "fail"


class RuleResult(BaseModel):
    code: str
    severity: Severity
    message: str
    document_id: str | None = None
    borrower_action: str | None = None  # what the borrower must do, if anything
    data: dict[str, str] = {}


class LoanStage(StrEnum):
    COLLECTING = "collecting_documents"
    NEEDS_REVIEW = "needs_processor_review"
    COMPLETE = "file_complete"


class Loan(BaseModel):
    id: str
    org_id: str
    borrower_name: str
    borrower_subject: str
    loan_officer: str
    monthly_debts: Decimal
    required_docs: list[DocType]
    stage: LoanStage = LoanStage.COLLECTING
    created_at: datetime
    last_activity_at: datetime
    telegram_chat_id: str | None = None


class LoanStatus(BaseModel):
    """Borrower-safe view of a loan: no other people's data, no internal notes."""

    loan_id: str
    stage: LoanStage
    documents_received: list[str]
    outstanding_items: list[str]


class DraftStatus(StrEnum):
    PENDING = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    SENT = "sent"


class MessageDraft(BaseModel):
    id: str
    loan_id: str
    body: str = Field(max_length=1500)
    status: DraftStatus = DraftStatus.PENDING
    created_by: str  # "conditions_agent", "hermes", a processor id...
    created_at: datetime
    request_key: str | None = None  # which outstanding items it asks for (dedupe)
    decided_by: str | None = None
    decided_at: datetime | None = None


class AuditEvent(BaseModel):
    at: datetime
    actor: str
    action: str
    loan_id: str | None = None
    org_id: str | None = None  # organization-level events (e.g. policy changes)
    detail: str = ""
