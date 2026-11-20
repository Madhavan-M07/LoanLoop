"""Architecture is enforced, not just documented: layers may only depend downward and the
business core (domain, rules) stays free of web/network/database libraries.
Contracts live in backend/pyproject.toml under [tool.importlinter].

Note: an earlier version ran `python -m importlinter.cli`, which imports the module and exits 0
without checking anything; the test passed even with a planted violation. Calling the real entry
point below was verified to FAIL on a deliberate rules -> data import.
"""

import os
from pathlib import Path

from importlinter.cli import lint_imports

BACKEND = Path(__file__).resolve().parents[1]


def test_import_contracts_hold():
    cwd = os.getcwd()
    os.chdir(BACKEND)  # contracts resolve the `app` package relative to the backend folder
    try:
        exit_code = lint_imports(config_filename=str(BACKEND / "pyproject.toml"), no_cache=True)
    finally:
        os.chdir(cwd)
    assert exit_code == 0, "layer contracts broken: run `uv run lint-imports` in backend/"
