"""Integration tests for FastAPI endpoints, error handling, CORS, caching, and rate limit."""

from __future__ import annotations

from pathlib import Path
import sys

from fastapi.testclient import TestClient

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from techcorp_analytics.api import create_app  # noqa: E402
from techcorp_analytics.config import Settings  # noqa: E402
from techcorp_analytics.database import initialize_database  # noqa: E402


def _build_test_client(
    tmp_path: Path,
    *,
    rate_limit_requests: int = 120,
    db_override: str | None = None,
) -> TestClient:
    db_path = db_override or str(tmp_path / "api_test.sqlite")
    if db_override is None:
        initialize_database(db_path, seed=True)
    settings = Settings(
        db_path=db_path,
        cors_origins=("http://localhost:3000",),
        rate_limit_requests=rate_limit_requests,
        rate_limit_window_seconds=60.0,
        cache_ttl_seconds=60.0,
    )
    app = create_app(settings=settings)
    return TestClient(app, raise_server_exceptions=False)


def test_health_endpoint_returns_ready_state(tmp_path: Path) -> None:
    """GET /health returns 200 with verified foreign keys and table counts."""
    client = _build_test_client(tmp_path)
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "healthy"
    assert body["database_ok"] is True
    assert body["foreign_keys_enabled"] is True
    assert body["counts"] == {"departments": 5, "employees": 10, "projects": 6}


def test_analytics_endpoints_return_expected_payloads(tmp_path: Path) -> None:
    """Analytics and employee directory endpoints return structured TechCorp insights."""
    client = _build_test_client(tmp_path)

    budgets_resp = client.get("/departments/budgets")
    assert budgets_resp.status_code == 200
    assert budgets_resp.json()[0]["department_name"] == "IT"

    headcount_resp = client.get("/departments/headcount")
    assert headcount_resp.status_code == 200
    assert headcount_resp.json()[0]["total_employees"] == 3

    durations_resp = client.get("/projects/durations")
    assert durations_resp.status_code == 200
    assert len(durations_resp.json()) == 6

    hv_resp = client.get("/projects/high-value?min_budget=25000")
    assert hv_resp.status_code == 200
    assert len(hv_resp.json()) == 3

    gov_resp = client.get("/governance")
    assert gov_resp.status_code == 200
    assert len(gov_resp.json()) == 3

    emp_resp = client.get("/employees?department=IT")
    assert emp_resp.status_code == 200
    assert len(emp_resp.json()) == 3


def test_budget_update_invalidates_analyze_cache(tmp_path: Path) -> None:
    """PATCH /projects/{id}/budget updates DB, invalidates cache, and rejects bad inputs."""
    client = _build_test_client(tmp_path)

    initial_summary = client.get("/analyze").json()
    assert initial_summary["totals"]["total_budget"] == 210000.0
    # Second GET hits cache cleanly
    assert client.get("/analyze").json()["totals"]["total_budget"] == 210000.0

    patch_resp = client.patch("/projects/201/budget", json={"budget": 60000.0})
    assert patch_resp.status_code == 200
    assert patch_resp.json()["previous_budget"] == 50000.0
    assert patch_resp.json()["budget"] == 60000.0

    refreshed_summary = client.get("/analyze").json()
    assert refreshed_summary["totals"]["total_budget"] == 220000.0

    missing_resp = client.patch("/projects/999/budget", json={"budget": 1000.0})
    assert missing_resp.status_code == 404

    invalid_resp = client.patch("/projects/201/budget", json={"budget": -10.0})
    assert invalid_resp.status_code == 422


def test_offboard_employee_endpoint_handles_happy_and_missing(tmp_path: Path) -> None:
    """DELETE /employees/{id} offboards existing employee and returns 404 on repeat."""
    client = _build_test_client(tmp_path)

    first = client.delete("/employees/110")
    assert first.status_code == 200
    assert first.json() == {"employee_id": 110, "offboarded": True}

    second = client.delete("/employees/110")
    assert second.status_code == 404


def test_cors_headers_and_rate_limiter_enforced(tmp_path: Path) -> None:
    """Configured CORS origin receives allow header and rate limiter enforces 429 limit."""
    client = _build_test_client(tmp_path, rate_limit_requests=2)

    r1 = client.get("/health", headers={"Origin": "http://localhost:3000"})
    assert r1.status_code == 200
    assert r1.headers.get("access-control-allow-origin") == "http://localhost:3000"

    r2 = client.get("/departments/budgets")
    assert r2.status_code == 200

    r3 = client.get("/departments/headcount")
    assert r3.status_code == 429
    assert "Too many requests" in r3.json()["detail"]


def test_domain_and_unhandled_exceptions_never_leak_stack_traces(tmp_path: Path) -> None:
    """Invalid query params return 422 and unexpected DB failures return generic 500 JSON."""
    client = _build_test_client(tmp_path)

    bad_date = client.get("/governance?senior_cutoff=not-a-date")
    assert bad_date.status_code == 422

    broken_db = tmp_path / "unmigrated.sqlite"
    broken_db.touch()
    broken_client = _build_test_client(tmp_path, db_override=str(broken_db))
    health_err = broken_client.get("/health")
    assert health_err.status_code == 400

    def _raise_boom() -> None:
        raise RuntimeError("sensitive internal connection detail")

    app = create_app(Settings(db_path=str(tmp_path / "api_test.sqlite"), rate_limit_requests=120))
    from techcorp_analytics.api import _get_db_connection

    app.dependency_overrides[_get_db_connection] = _raise_boom
    boom_client = TestClient(app, raise_server_exceptions=False)
    err_resp = boom_client.get("/health")
    assert err_resp.status_code == 500
    assert err_resp.json() == {"detail": "Internal server error."}
