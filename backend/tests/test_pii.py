from datetime import date

from app.security.pii import mask_for_log, tokenize
from tests.synthetic import bank_statement, paystub


def test_ssn_account_routing_are_tokenized_and_rehydrated():
    text = bank_statement(holder="Priya Sharma", bank="First Demo Bank", end=date(2026, 10, 31))
    text += "\nSSN 123-45-6789, call 555-201-3344, email priya@example.com"
    masked, vault = tokenize(text)
    for secret in ["123-45-6789", "000123456789", "021000021", "555-201-3344", "priya@example.com"]:
        assert secret not in masked
    assert set(vault.kinds) == {"ACCT", "EMAIL", "PHONE", "ROUTING", "SSN"}
    assert vault.rehydrate(masked) == text


def test_same_value_gets_same_token():
    masked, vault = tokenize("SSN: 123-45-6789 again 123-45-6789")
    assert masked.count("<SSN_1>") == 2 and len(vault.values) == 1


def test_invalid_routing_checksum_is_not_masked():
    masked, _ = tokenize("Routing Number: 123456789")
    assert "123456789" in masked  # fails ABA checksum: not a routing number


def test_amounts_and_dates_are_kept_for_the_llm():
    masked, _ = tokenize(paystub(employee="P", employer="E", pay_date=date(2026, 11, 14)))
    assert "2026-11-14" in masked and "$3,200.00" in masked


def test_mask_for_log_is_irreversible():
    out = mask_for_log("SSN 123-45-6789")
    assert "123-45-6789" not in out and "[SSN]" in out
