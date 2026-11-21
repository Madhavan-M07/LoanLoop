from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from app.domain.models import (
    BankStatementFields,
    DocStatus,
    DocType,
    Document,
    LenderPolicy,
    Loan,
    PaystubFields,
    Severity,
    W2Fields,
)
from app.rules.engine import (
    borrower_actions,
    dti,
    evaluate_loan,
    monthly_income_from_paystub,
    normalize_name,
)

TODAY = date(2026, 11, 20)
# Explicit test policy: the engine has no defaults of its own.
POLICY = LenderPolicy(
    paystub_max_age_days=30,
    bank_statement_max_age_days=60,
    w2_max_years_back=2,
    max_dti=Decimal("0.43"),
)
T0 = datetime(2026, 11, 1, tzinfo=UTC)


def loan(debts: str = "1450.00") -> Loan:
    return Loan(
        id="L-1",
        org_id="o",
        borrower_name="Priya Sharma",
        borrower_subject="b",
        loan_officer="lo",
        monthly_debts=Decimal(debts),
        required_docs=[DocType.PAYSTUB, DocType.W2, DocType.BANK_STATEMENT],
        created_at=T0,
        last_activity_at=T0,
    )


def doc(fields, i: int = 1) -> Document:
    kind = {
        PaystubFields: DocType.PAYSTUB,
        W2Fields: DocType.W2,
        BankStatementFields: DocType.BANK_STATEMENT,
    }[type(fields)]
    return Document(
        id=f"D{i}",
        loan_id="L-1",
        filename="f",
        status=DocStatus.EXTRACTED,
        doc_type=kind,
        fields=fields,
        uploaded_by="u",
        uploaded_at=T0,
    )


def stub(
    pay_date: date = date(2026, 11, 14),
    employer="Acme Robotics Inc.",
    gross="3200.00",
    net="2450.18",
    freq="biweekly",
    name="Priya Sharma",
) -> PaystubFields:
    return PaystubFields(
        employee_name=name,
        employer_name=employer,
        pay_date=pay_date,
        pay_frequency=freq,
        gross_pay=Decimal(gross),
        net_pay=Decimal(net),
        ytd_gross=Decimal("60800.00"),
    )


def w2(employer="Acme Robotics, LLC", year=2025) -> W2Fields:
    return W2Fields(
        employee_name="Priya Sharma",
        employer_name=employer,
        tax_year=year,
        wages=Decimal("81250.00"),
    )


def bank(end: date = date(2026, 10, 31)) -> BankStatementFields:
    return BankStatementFields(
        account_holder="Priya Sharma",
        bank_name="First Demo Bank",
        statement_end_date=end,
        ending_balance=Decimal("18450.22"),
    )


def codes(results):
    return {r.code for r in results}


def test_complete_clean_file_has_no_failures():
    res = evaluate_loan(loan(), [doc(stub(), 1), doc(w2(), 2), doc(bank(), 3)], TODAY, POLICY)
    assert not [r for r in res if r.severity != Severity.PASS]
    assert borrower_actions(res) == []


def test_missing_documents_create_borrower_actions():
    res = evaluate_loan(loan(), [doc(stub())], TODAY, POLICY)
    assert {"missing_w2", "missing_bank_statement"} <= codes(res)
    assert len(borrower_actions(res)) == 2


@pytest.mark.parametrize(
    ("pay_date", "expired"),
    [
        (date(2026, 10, 21), False),  # exactly 30 days: still OK
        (date(2026, 10, 20), True),  # 31 days: expired
    ],
)
def test_paystub_age_boundary(pay_date, expired):
    res = evaluate_loan(loan(), [doc(stub(pay_date=pay_date))], TODAY, POLICY)
    assert ("paystub_expired" in codes(res)) is expired


def test_future_pay_date_fails():
    assert "paystub_future_date" in codes(
        evaluate_loan(loan(), [doc(stub(pay_date=date(2026, 12, 1)))], TODAY, POLICY)
    )


def test_net_greater_than_gross_fails():
    assert "paystub_amounts_inconsistent" in codes(
        evaluate_loan(loan(), [doc(stub(gross="1000", net="1200"))], TODAY, POLICY)
    )


def test_employer_suffix_differences_are_not_a_mismatch():
    assert normalize_name("Acme Robotics Inc.") == normalize_name("ACME ROBOTICS, LLC")
    res = evaluate_loan(loan(), [doc(stub(), 1), doc(w2(), 2)], TODAY, POLICY)
    assert "employer_mismatch" not in codes(res)


def test_real_employer_change_is_flagged_for_processor_not_borrower():
    res = evaluate_loan(
        loan(), [doc(stub(employer="Globex Corp"), 1), doc(w2(), 2), doc(bank(), 3)], TODAY, POLICY
    )
    mm = [r for r in res if r.code == "employer_mismatch"]
    assert mm and mm[0].severity == Severity.WARN and mm[0].borrower_action is None


def test_name_mismatch_warns():
    assert "name_mismatch" in codes(
        evaluate_loan(loan(), [doc(stub(name="Someone Else"))], TODAY, POLICY)
    )


def test_old_bank_statement_and_w2():
    res = evaluate_loan(
        loan(), [doc(w2(year=2023), 1), doc(bank(end=date(2026, 9, 1)), 2)], TODAY, POLICY
    )
    assert {"w2_too_old", "bank_statement_expired"} <= codes(res)


@pytest.mark.parametrize(
    ("freq", "gross", "monthly"),
    [
        ("weekly", "1000.00", "4333.33"),
        ("biweekly", "3200.00", "6933.33"),
        ("semimonthly", "3000.00", "6000.00"),
        ("monthly", "5000.00", "5000.00"),
    ],
)
def test_monthly_income_by_frequency(freq, gross, monthly):
    assert monthly_income_from_paystub(stub(freq=freq, gross=gross, net="1")) == Decimal(monthly)


def test_dti_rounding_and_zero_income():
    assert dti(Decimal("1450.00"), Decimal("6933.33")) == Decimal("0.209")
    assert dti(Decimal("100"), Decimal("0")) is None


def test_dti_above_policy_is_warning_not_decision():
    res = evaluate_loan(loan(debts="3500.00"), [doc(stub())], TODAY, POLICY)
    r = next(r for r in res if r.code == "dti_above_policy")
    assert r.severity == Severity.WARN and r.borrower_action is None


def test_rules_are_deterministic():
    docs = [doc(stub(), 1), doc(w2(employer="Globex"), 2)]
    assert evaluate_loan(loan(), docs, TODAY, POLICY) == evaluate_loan(loan(), docs, TODAY, POLICY)


def test_unextracted_documents_are_ignored():
    d = doc(stub())
    d.status = DocStatus.NEEDS_REVIEW
    assert "missing_paystub" in codes(evaluate_loan(loan(), [d], TODAY, POLICY))


def test_thresholds_come_from_the_policy_not_the_code():
    lenient = POLICY.model_copy(update={"paystub_max_age_days": 45})
    old_stub = [doc(stub(pay_date=date(2026, 10, 10)))]  # 41 days old
    assert "paystub_expired" in codes(evaluate_loan(loan(), old_stub, TODAY, POLICY))
    assert "paystub_expired" not in codes(evaluate_loan(loan(), old_stub, TODAY, lenient))


def test_w2_years_back_from_policy():
    strict = POLICY.model_copy(update={"w2_max_years_back": 1})
    docs = [doc(w2(year=2024))]
    assert "w2_too_old" not in codes(evaluate_loan(loan(), docs, TODAY, POLICY))
    assert "w2_too_old" in codes(evaluate_loan(loan(), docs, TODAY, strict))


@pytest.mark.parametrize(
    "bad",
    [{"paystub_max_age_days": 0}, {"max_dti": Decimal("1.5")}, {"w2_max_years_back": -1}],
)
def test_policy_rejects_nonsense_values(bad):
    with pytest.raises(ValueError):
        LenderPolicy(**{**POLICY.model_dump(), **bad})


def test_policy_rejects_unknown_fields():
    with pytest.raises(ValueError):
        LenderPolicy(**POLICY.model_dump(), paystub_max_age_dayz=10)


# ---- Superseded documents: a newer document of the same type replaces older ones for
# recency checks. Integrity checks (fraud signals) still run on every document.


@pytest.mark.parametrize(
    ("old", "new", "expired_code"),
    [
        (stub(pay_date=date(2026, 9, 30)), stub(pay_date=date(2026, 11, 14)), "paystub_expired"),
        (bank(end=date(2026, 8, 31)), bank(end=date(2026, 10, 31)), "bank_statement_expired"),
        (w2(year=2022), w2(year=2025), "w2_too_old"),
    ],
)
@pytest.mark.parametrize("old_first", [True, False])  # upload order must not matter
def test_newer_document_supersedes_an_expired_one(old, new, expired_code, old_first):
    pair = [doc(old, 1), doc(new, 2)] if old_first else [doc(new, 2), doc(old, 1)]
    res = evaluate_loan(loan(), pair, TODAY, POLICY)
    assert expired_code not in codes(res)
    assert borrower_actions(res) == [] or all("missing" in r.code for r in res if r.borrower_action)
    sup = [r for r in res if r.code == "document_superseded"]
    assert [(r.document_id, r.severity) for r in sup] == [("D1", Severity.PASS)]
    assert "D2" in sup[0].message


def test_only_the_newest_expired_document_is_reported():
    docs = [doc(stub(pay_date=date(2026, 8, 1)), 1), doc(stub(pay_date=date(2026, 9, 30)), 2)]
    res = evaluate_loan(loan(), docs, TODAY, POLICY)
    expired = [r for r in res if r.code == "paystub_expired"]
    assert [r.document_id for r in expired] == ["D2"]
    assert len(borrower_actions(res)) == 3  # paystub + missing W-2 + missing bank statement


def test_integrity_checks_still_run_on_superseded_documents():
    docs = [
        doc(stub(pay_date=date(2026, 9, 30), gross="1000", net="1200"), 1),
        doc(stub(pay_date=date(2026, 11, 14)), 2),
    ]
    res = evaluate_loan(loan(), docs, TODAY, POLICY)
    bad = [r for r in res if r.code == "paystub_amounts_inconsistent"]
    assert [r.document_id for r in bad] == ["D1"]


def test_single_document_is_never_marked_superseded():
    res = evaluate_loan(loan(), [doc(stub(), 1), doc(w2(), 2), doc(bank(), 3)], TODAY, POLICY)
    assert "document_superseded" not in codes(res)


def test_ytd_below_current_pay_warns_processor_not_borrower():
    s = stub().model_copy(update={"ytd_gross": Decimal("1000.00")})  # gross is 3200.00
    res = evaluate_loan(loan(), [doc(s)], TODAY, POLICY)
    r = next(r for r in res if r.code == "paystub_ytd_below_current")
    assert r.severity == Severity.WARN and r.borrower_action is None
