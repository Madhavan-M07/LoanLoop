"""Shared helpers for LoanLoop Claude Code hooks (stdlib only, cross-platform)."""
import json
import os
import shutil
import subprocess
import sys

def _native(path: str) -> str:
    """Convert Git-Bash/MSYS paths like /c/Users/x to C:/Users/x on Windows."""
    if os.name == "nt" and len(path) > 2 and path[0] == "/" and path[2] == "/" and path[1].isalpha():
        return f"{path[1].upper()}:{path[2:]}"
    return path


PROJECT_DIR = os.path.abspath(_native(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()))


def read_input() -> dict:
    try:
        return json.load(sys.stdin)
    except Exception:
        return {}


def decide(decision: str, reason: str) -> None:
    """PreToolUse decision: 'allow' | 'deny' | 'ask'."""
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,
            "permissionDecisionReason": reason,
        }
    }))
    sys.exit(0)


def block(message: str) -> None:
    """Exit code 2: stderr is fed back to Claude so it can fix the problem."""
    print(message, file=sys.stderr)
    sys.exit(2)


def which(cmd: str) -> str | None:
    return shutil.which(cmd)


def run(args: list[str], cwd: str | None = None, timeout: int = 240) -> tuple[int, str]:
    try:
        p = subprocess.run(args, cwd=cwd or PROJECT_DIR, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout + p.stderr)
    except subprocess.TimeoutExpired:
        return 124, f"timed out after {timeout}s: {' '.join(args)}"
    except FileNotFoundError as e:
        return 127, str(e)


def rel(path: str) -> str:
    try:
        return os.path.relpath(os.path.abspath(_native(path)), PROJECT_DIR).replace("\\", "/")
    except ValueError:
        return path.replace("\\", "/")
