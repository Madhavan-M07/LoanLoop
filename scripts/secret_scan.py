"""Block secrets from entering git. Dependency-free; runs as a pre-commit hook.

Usage:
  python scripts/secret_scan.py --staged   # scan lines being committed (pre-commit hook)
  python scripts/secret_scan.py --all      # scan every tracked file (CI / one-off audit)

Exit code 1 if anything is found. To allow a known false positive, put
`secret-scan: allow` on that line. CI will additionally run gitleaks (broader ruleset).
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import PurePosixPath

# Specific, low-false-positive patterns for credentials this project actually uses or could.
PATTERNS: dict[str, re.Pattern[str]] = {
    "Google API key": re.compile(r"AIza[0-9A-Za-z_\-]{35}"),
    "Google auth token": re.compile(r"\bAQ\.[0-9A-Za-z_\-\.]{30,}"),
    "OpenAI/OpenRouter key": re.compile(r"\bsk-(?:or-v1-|proj-)?[0-9A-Za-z_\-]{20,}"),
    "Groq key": re.compile(r"\bgsk_[0-9A-Za-z]{20,}"),
    "GitHub token": re.compile(r"\bgh[pousr]_[0-9A-Za-z]{30,}"),
    "Slack token": re.compile(r"\bxox[abprs]-[0-9A-Za-z\-]{10,}"),
    "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "Telegram bot token": re.compile(r"\b\d{8,10}:[0-9A-Za-z_\-]{35}\b"),
    "Private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
}
ALLOW_MARKER = "secret-scan: allow"

# Files that must never be committed at all, whatever they contain.
FORBIDDEN_FILE = re.compile(r"(^|/)\.env(\.(?!example$)[^/]+)?$|\.(pem|key|p12|pfx)$")


@dataclass(frozen=True)
class Finding:
    path: str
    line_no: int | None
    kind: str

    def __str__(self) -> str:
        where = f"{self.path}:{self.line_no}" if self.line_no else self.path
        return f"  {where}  ->  {self.kind}"


def scan_text(path: str, text: str, line_offset: int = 0) -> list[Finding]:
    findings = []
    for i, line in enumerate(text.splitlines(), start=1):
        if ALLOW_MARKER in line:
            continue
        for kind, rx in PATTERNS.items():
            if rx.search(line):
                findings.append(Finding(path, i + line_offset, kind))
    return findings


def check_filename(path: str) -> list[Finding]:
    p = str(PurePosixPath(path))
    return (
        [Finding(p, None, "file type must never be committed")] if FORBIDDEN_FILE.search(p) else []
    )


def _git(*args: str) -> str:
    git = shutil.which("git")  # absolute path: don't run whatever "git" is first on PATH
    if git is None:
        raise SystemExit("secret_scan: git not found")
    return subprocess.run(  # noqa: S603 - fixed git arguments, no user input
        [git, *args],
        capture_output=True,
        text=True,
        check=True,
        encoding="utf-8",
        errors="replace",
    ).stdout


def scan_staged() -> list[Finding]:
    findings: list[Finding] = []
    for path in _git("diff", "--cached", "--name-only", "--diff-filter=ACMR").splitlines():
        findings += check_filename(path)
    current, line_no = "", 0
    for line in _git("diff", "--cached", "-U0", "--no-color", "--diff-filter=ACMR").splitlines():
        if line.startswith("+++ "):
            current = line[6:] if line.startswith("+++ b/") else line[4:]
        elif line.startswith("@@"):
            m = re.search(r"\+(\d+)", line)
            line_no = int(m.group(1)) - 1 if m else 0
        elif line.startswith("+"):
            line_no += 1
            findings += scan_text(current, line[1:], line_offset=line_no - 1)
    return findings


def scan_all() -> list[Finding]:
    findings: list[Finding] = []
    for path in _git("ls-files").splitlines():
        findings += check_filename(path)
        try:
            with open(path, encoding="utf-8") as f:
                findings += scan_text(path, f.read())
        except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError):
            continue  # binary or removed file
    return findings


def main(argv: list[str]) -> int:
    mode = argv[1] if len(argv) > 1 else "--staged"
    findings = scan_all() if mode == "--all" else scan_staged()
    if not findings:
        return 0
    print("\nSECRET SCAN: commit blocked. Possible secrets found:\n", file=sys.stderr)
    for f in findings:
        print(f, file=sys.stderr)
    print(
        "\nPut secrets in backend/.env (git-ignored), never in tracked files.\n"
        "If a real key was exposed, rotate it. For a false positive, add "
        f"'{ALLOW_MARKER}' to that line.\n",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
