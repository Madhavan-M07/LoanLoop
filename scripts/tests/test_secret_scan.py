"""Fake secrets are BUILT at runtime (string concatenation) so this file never contains a
real-looking key itself and does not trip the scanner it tests."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from secret_scan import check_filename, scan_text  # noqa: E402

FAKES = {
    "Google API key": "AIza" + "B" * 35,
    "Google auth token": "AQ." + "Ab8RN6" + "x" * 30,
    "OpenAI/OpenRouter key": "sk-or-v1-" + "a1" * 15,
    "Groq key": "gsk_" + "Z9" * 15,
    "GitHub token": "ghp_" + "q" * 36,
    "AWS access key": "AKIA" + "ABCDEFGHIJKLMNOP",
    "Telegram bot token": "123456789:" + "A" * 35,
    "Private key": "-----BEGIN " + "PRIVATE KEY-----",
}


@pytest.mark.parametrize(("kind", "secret"), FAKES.items())
def test_detects_each_secret_type(kind, secret):
    found = scan_text("backend/.env.example", f"SOME_VAR={secret}\n")
    assert [f.kind for f in found] == [kind]


def test_reports_correct_line_number():
    text = "ok line\nGEMINI_API_KEY=" + FAKES["Google API key"] + "\n"
    assert scan_text("x.py", text)[0].line_no == 2


def test_bare_key_line_like_the_real_incident_is_caught():
    # A key pasted on its own line with no variable name (how the real incident happened).
    assert scan_text("backend/.env.example", FAKES["Google auth token"] + "\n")


@pytest.mark.parametrize(
    "safe",
    [
        "GEMINI_API_KEY=",
        "GEMINI_API_KEY=paste-your-key-here",
        'api_key_env: "GEMINI_API_KEY"',
        'LOANLOOP_PRINCIPALS_JSON={"dev-processor-acme": {}}',
        'ssn: str = "123-45-6789"',
    ],
)
def test_placeholders_and_normal_code_are_not_flagged(safe):
    assert scan_text("f", safe) == []


def test_allow_marker_skips_a_known_false_positive():
    line = "example = '" + FAKES["Groq key"] + "'  # secret-scan: allow"
    assert scan_text("docs.md", line) == []


@pytest.mark.parametrize(
    ("path", "blocked"),
    [
        ("backend/.env", True),
        (".env", True),
        ("backend/.env.local", True),
        ("certs/server.pem", True),
        ("deploy/id.key", True),
        ("backend/.env.example", False),
        ("backend/app/core/config.py", False),
    ],
)
def test_forbidden_files(path, blocked):
    assert bool(check_filename(path)) is blocked
