"""Deterministic rules engine. Pure functions: no I/O, no LLM, fully unit-tested.

The LLM reads documents; THIS code decides whether they pass. Thresholds are lender policy
(configurable), not model output.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from app.domain.models import (
    BankStatementFields,
    DocStatus,
    DocType,
    Document,
    Loan,
    PaystubFields,
    RuleResult,
    Severity,
    W2Fields,
)

PERIODS_PER_YEAR = {"weekly": 52, "biweekly": 26, "semimonthly": 24, "monthly": 12}


@dataclass(frozen=True)
class LenderPolicy:
    paystub_max_age_days: int = 30
    bank_statement_max_age_days: int = 60
    max_dti: Decimal = Decimal("0.43")


DEFAULT_POLICY = LenderPolicy()

_SUFFIXES = re.compile(r"\b(inc|llc|ltd|corp|corporation|co|company)\b\.?", re.I)


def normalize_name(name: str) -> str:
    name = _SUFFIXES.sub("", name.lower())
    return re.sub(r"[^a-z0-9]+", " ", name).strip()


def monthly_income_from_paystub(p: PaystubFields) -> Decimal:
    annual = p.gross_pay * PERIODS_PER_YEAR[p.pay_frequency]
    return (annual / 12).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def dti(monthly_debts: Decimal, monthly_income: Decimal) -> Decimal | None:
    if monthly_income <= 0:
        return None
    return (monthly_debts / monthly_income).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


def _latest[T](docs: list[Document], kind: type[T], key: str) -> tuple[Document, T] | None:
    pairs = [(d, d.fields) for d in docs if isinstance(d.fields, kind)]
    if not pairs:
        return None
    return max(pairs, key=lambda p: getattr(p[1], key))  # type: ignore[return-value]


def check_paystub(
    doc: Document, p: PaystubFields, as_of: date, pol: LenderPolicy
) -> list[RuleResult]:
    out: list[RuleResult] = []
    if p.pay_date > as_of:
        out.append(
            RuleResult(
                code="paystub_future_date",
                severity=Severity.FAIL,
                document_id=doc.id,
                message=f"Pay date {p.pay_date} is in the future.",
            )
        )
    age = (as_of - p.pay_date).days
    if age > pol.paystub_max_age_days:
        out.append(
            RuleResult(
                code="paystub_expired",
                severity=Severity.FAIL,
                document_id=doc.id,
                message=f"Paystub is {age} days old (max {pol.paystub_max_age_days}).",
                borrower_action="Send your most recent paystub (dated within the last "
                f"{pol.paystub_max_age_days} days).",
                data={"age_days": str(age)},
            )
        )
    if p.gross_pay <= 0 or p.net_pay < 0 or p.net_pay > p.gross_pay:
        out.append(
            RuleResult(
                code="paystub_amounts_inconsistent",
                severity=Severity.FAIL,
                document_id=doc.id,
                message=f"Gross {p.gross_pay} / net {p.net_pay} are inconsistent.",
            )
        )
    if p.ytd_gross is not None and p.ytd_gross < p.gross_pay:
        out.append(
            RuleResult(
                code="paystub_ytd_below_current",
                severity=Severity.WARN,
                document_id=doc.id,
                message="YTD gross is lower than current gross.",
            )
        )
    return out


def evaluate_loan(
    loan: Loan, docs: list[Document], as_of: date, pol: LenderPolicy = DEFAULT_POLICY
) -> list[RuleResult]:
    """All rule results for a loan file. Same inputs -> same outputs, always."""
    results: list[RuleResult] = []
    usable = [d for d in docs if d.status == DocStatus.EXTRACTED]

    # 1. Required documents present
    have = {d.doc_type for d in usable}
    labels = {
        DocType.PAYSTUB: "a recent paystub",
        DocType.W2: f"your {as_of.year - 1} W-2",
        DocType.BANK_STATEMENT: "your latest bank statement",
    }
    for req in loan.required_docs:
        if req not in have:
            results.append(
                RuleResult(
                    code=f"missing_{req.value}",
                    severity=Severity.FAIL,
                    message=f"No usable {req.value} on file.",
                    borrower_action=f"Send {labels[req]}.",
                )
            )

    # 2. Per-document checks
    for d in usable:
        if isinstance(d.fields, PaystubFields):
            results += check_paystub(d, d.fields, as_of, pol)
        elif isinstance(d.fields, BankStatementFields):
            age = (as_of - d.fields.statement_end_date).days
            if age > pol.bank_statement_max_age_days:
                results.append(
                    RuleResult(
                        code="bank_statement_expired",
                        severity=Severity.FAIL,
                        document_id=d.id,
                        message=f"Bank statement is {age} days old "
                        f"(max {pol.bank_statement_max_age_days}).",
                        borrower_action="Send your most recent bank statement.",
                    )
                )
        elif isinstance(d.fields, W2Fields) and d.fields.tax_year < as_of.year - 2:
            results.append(
                RuleResult(
                    code="w2_too_old",
                    severity=Severity.FAIL,
                    document_id=d.id,
                    message=f"W-2 is for {d.fields.tax_year}.",
                    borrower_action=f"Send your {as_of.year - 1} W-2.",
                )
            )

    # 3. Cross-document consistency
    stub = _latest(usable, PaystubFields, "pay_date")
    w2 = _latest(usable, W2Fields, "tax_year")
    if stub and w2 and normalize_name(stub[1].employer_name) != normalize_name(w2[1].employer_name):
        results.append(
            RuleResult(
                code="employer_mismatch",
                severity=Severity.WARN,
                document_id=stub[0].id,
                message=f"Paystub employer '{stub[1].employer_name}' differs from W-2 employer "
                f"'{w2[1].employer_name}'. Processor to confirm job change or error.",
            )
        )
    for d in usable:
        name = getattr(d.fields, "employee_name", None) or getattr(d.fields, "account_holder", None)
        if name and normalize_name(name) != normalize_name(loan.borrower_name):
            results.append(
                RuleResult(
                    code="name_mismatch",
                    severity=Severity.WARN,
                    document_id=d.id,
                    message=f"Name on {d.doc_type.value} does not match borrower.",
                )
            )

    # 4. Income & DTI (computed, reported; a human decides what it means)
    if stub:
        income = monthly_income_from_paystub(stub[1])
        ratio = dti(loan.monthly_debts, income)
        data = {"monthly_income": str(income), "dti": str(ratio)}
        if ratio is not None and ratio > pol.max_dti:
            results.append(
                RuleResult(
                    code="dti_above_policy",
                    severity=Severity.WARN,
                    data=data,
                    message=f"DTI {ratio} exceeds lender policy {pol.max_dti}.",
                )
            )
        else:
            results.append(
                RuleResult(
                    code="income_calculated",
                    severity=Severity.PASS,
                    data=data,
                    message=f"Monthly income {income}, DTI {ratio}.",
                )
            )
    return results


def borrower_actions(results: list[RuleResult]) -> list[str]:
    seen: list[str] = []
    for r in results:
        if r.severity == Severity.FAIL and r.borrower_action and r.borrower_action not in seen:
            seen.append(r.borrower_action)
    return seen
