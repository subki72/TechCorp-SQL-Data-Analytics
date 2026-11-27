"""Unit tests for TechCorp BI analytics queries, caching, and governance reporting."""

from __future__ import annotations

from pathlib import Path
import sqlite3
import sys
import time

import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from techcorp_analytics.analytics import AnalyticsCache, TechCorpAnalytics  # noqa: E402
from techcorp_analytics.database import (  # noqa: E402
    ValidationError,
    apply_migrations,
    seed_techcorp_data,
)
from techcorp_analytics.repository import TechCorpRepository  # noqa: E402


def _seeded_analytics_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    apply_migrations(conn)
    seed_techcorp_data(conn)
    return conn


def test_department_budget_summary_includes_zero_project_departments() -> None:
    """Budget aggregation ranks IT highest and retains empty departments with zero totals."""
    conn = _seeded_analytics_conn()
    try:
        TechCorpRepository(conn).add_department(6, "Legal")
        analytics = TechCorpAnalytics(conn)
        summary = analytics.department_budget_summary()

        assert summary[0]["department_name"] == "IT"
        assert summary[0]["total_projects"] == 2
        assert summary[0]["total_budget"] == 130000.0
        legal = next(item for item in summary if item["department_name"] == "Legal")
        assert legal["total_projects"] == 0
        assert legal["total_budget"] == 0.0
    finally:
        conn.close()


def test_high_value_projects_strict_and_inclusive_thresholds() -> None:
    """High-value project filter handles strict >, inclusive >=, and negative validation."""
    conn = _seeded_analytics_conn()
    try:
        analytics = TechCorpAnalytics(conn)
        strict_items = analytics.high_value_projects(min_budget=25000.0)
        inclusive_items = analytics.high_value_projects(min_budget=25000.0, inclusive=True)

        assert [item["project_name"] for item in strict_items] == [
            "App Development",
            "Website Redesign",
            "Sales Strategy",
        ]
        assert len(inclusive_items) == 4
        assert any(item["project_name"] == "Market Research" for item in inclusive_items)

        with pytest.raises(ValidationError):
            analytics.high_value_projects(min_budget=-100.0)
    finally:
        conn.close()


def test_headcount_by_department_reflects_offboarding() -> None:
    """Headcount metrics update accurately after employee offboarding."""
    conn = _seeded_analytics_conn()
    try:
        repo = TechCorpRepository(conn)
        analytics = TechCorpAnalytics(conn)

        initial = {
            item["department_name"]: item["total_employees"]
            for item in analytics.headcount_by_department()
        }
        assert initial == {
            "IT": 3,
            "Finance": 2,
            "Human Resources": 2,
            "Marketing": 2,
            "Sales": 1,
        }

        repo.offboard_employee(110, raise_if_missing=True)
        after = {
            item["department_name"]: item["total_employees"]
            for item in analytics.headcount_by_department()
        }
        assert after["Finance"] == 1
    finally:
        conn.close()


def test_project_duration_metrics_computes_julianday() -> None:
    """Duration analytics order longest timelines first via julianday calculations."""
    conn = _seeded_analytics_conn()
    try:
        durations = TechCorpAnalytics(conn).project_duration_metrics()
        assert len(durations) == 6
        assert durations[0]["duration_days"] == 213.0
        assert durations[-1]["project_name"] == "Financial Audit"
        assert durations[-1]["duration_days"] == 60.0
    finally:
        conn.close()


def test_executive_governance_report_and_date_validation() -> None:
    """Governance report maps senior leads hired before cutoff and rejects malformed dates."""
    conn = _seeded_analytics_conn()
    try:
        analytics = TechCorpAnalytics(conn)
        report = analytics.executive_governance_report(senior_cutoff="2021-01-01")
        assert len(report) == 3
        managers = {row["manager_name"] for row in report}
        assert managers == {"James Taylor", "Michael Brown"}

        with pytest.raises(ValidationError, match="YYYY-MM-DD"):
            analytics.executive_governance_report(senior_cutoff="2021/01/01")
    finally:
        conn.close()


def test_generate_full_summary_totals() -> None:
    """Full BI summary aggregates counts, total budget, and average duration accurately."""
    conn = _seeded_analytics_conn()
    try:
        summary = TechCorpAnalytics(conn).generate_full_summary()
        assert summary["totals"]["departments"] == 5
        assert summary["totals"]["employees"] == 10
        assert summary["totals"]["projects"] == 6
        assert summary["totals"]["total_budget"] == 210000.0
        assert summary["totals"]["average_project_duration_days"] > 100.0
    finally:
        conn.close()


def test_analytics_cache_ttl_expiration_and_clear() -> None:
    """AnalyticsCache serves cached items within TTL, expires cleanly, and clears on demand."""
    with pytest.raises(ValidationError):
        AnalyticsCache(ttl_seconds=-1.0)

    disabled_cache = AnalyticsCache(ttl_seconds=0.0)
    disabled_cache.set("k", {"v": 1})
    assert disabled_cache.get("k") is None

    cache = AnalyticsCache(ttl_seconds=0.05)
    cache.set("analyze", {"total": 100})
    assert cache.get("analyze") == {"total": 100}
    time.sleep(0.08)
    assert cache.get("analyze") is None

    cache.set("analyze", {"total": 200})
    cache.clear()
    assert cache.get("analyze") is None
