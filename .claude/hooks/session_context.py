"""SessionStart: print live repo state so Claude starts every session repo-aware."""

import os
import re

from _common import PROJECT_DIR, run

lines = ["## LoanLoop session context (auto-generated)"]

c, branch = run(["git", "branch", "--show-current"], timeout=10)
if c == 0:
    c2, status = run(["git", "status", "--porcelain"], timeout=10)
    n = len([s for s in status.splitlines() if s.strip()])
    lines.append(
        f"- Git branch: `{branch.strip() or '(no commits yet)'}`, {n} uncommitted change(s)"
    )
    c3, wt = run(["git", "worktree", "list"], timeout=10)
    if c3 == 0 and len(wt.splitlines()) > 1:
        lines.append(
            f"- Active worktrees: {len(wt.splitlines())} (parallel agent work in progress)"
        )

roadmap = os.path.join(PROJECT_DIR, "docs", "ROADMAP.md")
if os.path.exists(roadmap):
    with open(roadmap, encoding="utf-8") as f:
        todo = [m.group(1) for m in re.finditer(r"^- \[ \] (.+)$", f.read(), re.M)]
    if todo:
        lines.append("- Next roadmap items:")
        lines += [f"  - {t}" for t in todo[:5]]

log = os.path.join(PROJECT_DIR, "docs", "BUILD_LOG.md")
if os.path.exists(log):
    with open(log, encoding="utf-8") as f:
        entries = re.findall(r"^## (.+)$", f.read(), re.M)
    if entries:
        lines.append(f"- Last build-log entry: {entries[-1]}")

lines.append(
    "- Reminder: outcome first (O1–O6 in CLAUDE.md); verify with evidence before saying done."
)
print("\n".join(lines))
