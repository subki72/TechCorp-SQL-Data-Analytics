"""CLI, configuration, and patched Jupyter notebook regression tests."""

from __future__ import annotations

import ast
import json
from pathlib import Path
import sys

import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from main import main as cli_main  # noqa: E402
from techcorp_analytics.config import get_settings  # noqa: E402


def test_config_loads_env_overrides_and_rejects_bad_numbers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Environment overrides load cleanly while malformed numeric vars fail loudly."""
    monkeypatch.setenv("TECHCORP_DB_PATH", "custom.sqlite")
    monkeypatch.setenv("TECHCORP_API_PORT", "9001")
    monkeypatch.setenv("TECHCORP_REQUEST_TIMEOUT_SECONDS", "15.5")
    monkeypatch.setenv("TECHCORP_CORS_ORIGINS", "http://a.local, http://b.local")

    settings = get_settings()
    assert settings.db_path == "custom.sqlite"
    assert settings.api_port == 9001
    assert settings.request_timeout_seconds == 15.5
    assert settings.cors_origins == ("http://a.local", "http://b.local")

    monkeypatch.setenv("TECHCORP_API_PORT", "not-an-int")
    with pytest.raises(ValueError, match="TECHCORP_API_PORT"):
        get_settings()


def test_cli_health_check_read_only_and_memory(capsys: pytest.CaptureFixture[str]) -> None:
    """CLI --health works against :memory: and committed snapshot without mutating it."""
    code_mem = cli_main(["--health", "--db", ":memory:"])
    assert code_mem == 0
    mem_payload = json.loads(capsys.readouterr().out)
    assert mem_payload["status"] == "healthy"
    assert mem_payload["counts"]["employees"] == 10

    snapshot = ROOT_DIR / "techcorp_db.sqlite"
    if snapshot.exists():
        code_snap = cli_main(["--health", "--db", str(snapshot)])
        assert code_snap == 0
        snap_payload = json.loads(capsys.readouterr().out)
        assert snap_payload["status"] == "healthy"
        assert snap_payload["foreign_keys_enabled"] is True


def test_cli_health_missing_file_returns_nonzero(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """CLI --health exits with code 1 when pointed to a nonexistent SQLite file."""
    missing = tmp_path / "absent.sqlite"
    code = cli_main(["--health", "--db", str(missing)])
    assert code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "unhealthy"


def test_cli_demo_runs_offline_sandbox(capsys: pytest.CaptureFixture[str]) -> None:
    """CLI --demo executes complete TechCorp workflow in isolated :memory: DB."""
    code = cli_main(["--demo"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["mode"] == "sandbox_memory_demo"
    assert payload["foreign_key_enforced"] is True
    assert payload["it_employees_count"] == 3
    assert payload["updated_project"]["budget"] == 60000.0
    assert payload["offboarded_employee_110"] is True
    assert payload["summary"]["totals"]["employees"] == 9


def test_notebook_remediation_invariants_and_syntax() -> None:
    """Patched notebook contains all Stage 1 fixes and every code cell parses cleanly."""
    nb_path = ROOT_DIR / "Portfolio_V3_TechCorp_Engineering.ipynb"
    nb = json.loads(nb_path.read_text(encoding="utf-8"))
    code_cells = [c for c in nb["cells"] if c.get("cell_type") == "code"]
    joined = "\n".join("".join(c.get("source", [])) for c in code_cells)

    assert "PRAGMA foreign_keys = ON" in joined
    assert "DROP TABLE IF EXISTS Assignments" not in joined
    assert "DOCX Source" not in joined
    assert "hue='department_name'" in joined
    assert "legend=False" in joined
    assert "conn.close()" in joined
    assert "TECHCORP_NOTEBOOK_DB" in joined

    for idx, cell in enumerate(code_cells):
        src = "".join(cell.get("source", []))
        tree = ast.parse(src, filename=f"notebook_cell_{idx}.py")
        assert len(tree.body) > 0
