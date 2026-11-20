"""PostToolUse(Edit|Write|MultiEdit): auto-format, then report lint errors back to Claude.

Skips silently when the toolchain for that file isn't installed yet.
"""
import os

from _common import PROJECT_DIR, block, read_input, rel, run, which

data = read_input()
path = (data.get("tool_input") or {}).get("file_path", "")
if not path or not os.path.exists(path):
    raise SystemExit(0)

r = rel(path)
problems = []

if path.endswith(".py"):
    ruff = ["uv", "run", "ruff"] if which("uv") else (["ruff"] if which("ruff") else None)
    if ruff:
        run(ruff + ["format", path])
        code, out = run(ruff + ["check", "--fix", path])
        if code not in (0, 127):
            problems.append(f"ruff found issues in {r}:\n{out.strip()[-2000:]}")

elif path.endswith((".ts", ".tsx", ".js", ".jsx", ".css", ".json", ".md")) and r.startswith("frontend/"):
    bin_dir = os.path.join(PROJECT_DIR, "frontend", "node_modules", ".bin")
    prettier = os.path.join(bin_dir, "prettier.cmd" if os.name == "nt" else "prettier")
    eslint = os.path.join(bin_dir, "eslint.cmd" if os.name == "nt" else "eslint")
    if os.path.exists(prettier):
        run([prettier, "--write", path], cwd=os.path.join(PROJECT_DIR, "frontend"))
    if os.path.exists(eslint) and path.endswith((".ts", ".tsx")):
        code, out = run([eslint, "--fix", path], cwd=os.path.join(PROJECT_DIR, "frontend"))
        if code != 0:
            problems.append(f"eslint found issues in {r}:\n{out.strip()[-2000:]}")

if problems:
    block("\n\n".join(problems) + "\n\nFix these before moving on.")
