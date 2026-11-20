"""Stop: don't let Claude declare 'done' while tests for changed code are failing.

Runs only the suites for areas with uncommitted changes. Skips areas not scaffolded yet.
"""
import os

from _common import PROJECT_DIR, block, read_input, run, uv_cmd

data = read_input()
if data.get("stop_hook_active"):
    raise SystemExit(0)  # already re-prompted once; avoid infinite loops

code, out = run(["git", "status", "--porcelain"], timeout=20)
if code != 0:
    raise SystemExit(0)
changed = [line[3:].strip().strip('"').replace("\\", "/") for line in out.splitlines() if line.strip()]

failures = []

for area in ("backend", "mcp"):
    if not any(p.startswith(f"{area}/") and p.endswith(".py") for p in changed):
        continue
    area_dir = os.path.join(PROJECT_DIR, area)
    uv = uv_cmd()
    if not (uv and os.path.exists(os.path.join(area_dir, "pyproject.toml"))):
        continue
    c, o = run(uv + ["run", "pytest", "-q", "-x", "--no-header", "-p", "no:cacheprovider"],
               cwd=area_dir, timeout=240)
    if c not in (0, 5):  # 5 = no tests collected
        failures.append(f"[{area}] pytest failed:\n{o.strip()[-2500:]}")

if any(p.startswith("frontend/") and p.endswith((".ts", ".tsx")) for p in changed):
    fe = os.path.join(PROJECT_DIR, "frontend")
    if os.path.exists(os.path.join(fe, "node_modules")):
        npm = "npm.cmd" if os.name == "nt" else "npm"
        c, o = run([npm, "run", "typecheck", "--silent"], cwd=fe, timeout=180)
        if c != 0 and "Missing script" not in o:
            failures.append(f"[frontend] typecheck failed:\n{o.strip()[-2500:]}")

if failures:
    block("Verification failed. The task is not done:\n\n" + "\n\n".join(failures))
