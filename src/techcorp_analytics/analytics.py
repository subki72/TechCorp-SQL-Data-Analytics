"""Business Intelligence queries and governance analytics for TechCorp."""

from __future__ import annotations

import logging
import sqlite3
import threading
import time
from typing import Any

from techcorp_analytics.database import ValidationError
from techcorp_analytics.repository import validate_iso_date

logger = logging.getLogger(__name__)


class AnalyticsCache:
    """Thread-safe in-memory TTL cache for read-heavy analytics snapshots."""

    def __init__(self, ttl_seconds: float = 60.0) -> None:
        """Initialize cache with configurable time-to-live in seconds."""
        if ttl_seconds < 0:
            raise ValidationError(f"ttl_seconds must be >= 0, got {ttl_seconds}.")
        self._ttl_seconds = ttl_seconds
        self._lock = threading.Lock()
        self._store: dict[str, tuple[float, Any]] = {}

    def get(self, key: str) -> Any | None:
        """Return cached value if present and unexpired, else None."""
        if self._ttl_seconds == 0:
            return None
        now = time.monotonic()
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            expires_at, payload = entry
            if now >= expires_at:
                del self._store[key]
                return None
            return payload

    def set(self, key: str, value: Any) -> None:
        """Store payload in cache under ``key``."""
        if self._ttl_seconds == 0:
            return
        with self._lock:
            self._store[key] = (time.monotonic() + self._ttl_seconds, value)

    def clear(self) -> None:
        """Invalidate all cached entries."""
        with self._lock:
            self._store.clear()


class TechCorpAnalytics:
    """SQLite-backed BI analytics and executive governance reporting engine."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        """Initialize analytics engine with an active SQLite connection."""
        self._conn = conn
        self._conn.execute("PRAGMA foreign_keys = ON;")

    def department_budget_summary(self) -> list[dict[str, Any]]:
        """Aggregate project count and budget totals across departments."""
        rows = self._conn.execute(
            """
            SELECT
                d.department_id,
                d.department_name,
                COUNT(p.project_id) AS total_projects,
                COALESCE(SUM(p.budget), 0.0) AS total_budget,
                COALESCE(AVG(p.budget), 0.0) AS average_budget
            FROM Departments d
            LEFT JOIN Projects p ON d.department_id = p.department_id
            GROUP BY d.department_id, d.department_name
            ORDER BY total_budget DESC, d.department_name ASC;
            """
        ).fetchall()
        results = [
            {
                "department_id": int(row["department_id"]),
                "department_name": str(row["department_name"]),
                "total_projects": int(row["total_projects"]),
                "total_budget": round(float(row["total_budget"]), 2),
                "average_budget": round(float(row["average_budget"]), 2),
            }
            for row in rows
        ]
        logger.info("Computed department budget summary across %d departments", len(results))
        return results

    def high_value_projects(
        self,
        min_budget: float = 25000.0,
        *,
        inclusive: bool = False,
    ) -> list[dict[str, Any]]:
        """Identify projects exceeding (or meeting) a budget threshold.

        Args:
            min_budget: Budget threshold in USD (must be >= 0).
            inclusive: If True, uses ``>=`` comparison; defaults to strict ``>``.

        Returns:
            Matching projects ordered by budget descending.
        """
        if min_budget < 0:
            raise ValidationError(f"min_budget must be >= 0, got {min_budget}.")

        operator = ">=" if inclusive else ">"
        rows = self._conn.execute(
            f"""
            SELECT
                p.project_id,
                p.project_name,
                p.budget,
                p.start_date,
                p.end_date,
                d.department_name
            FROM Projects p
            JOIN Departments d ON p.department_id = d.department_id
            WHERE p.budget {operator} ?
            ORDER BY p.budget DESC, p.project_id ASC;
            """,
            (float(min_budget),),
        ).fetchall()
        results = [
            {
                "project_id": int(row["project_id"]),
                "project_name": str(row["project_name"]),
                "budget": round(float(row["budget"]), 2),
                "start_date": str(row["start_date"]),
                "end_date": str(row["end_date"]),
                "department_name": str(row["department_name"]),
            }
            for row in rows
        ]
        logger.info(
            "Found %d high-value projects (min_budget=%.2f, inclusive=%s)",
            len(results),
            min_budget,
            inclusive,
        )
        return results

    def headcount_by_department(self) -> list[dict[str, Any]]:
        """Calculate employee headcount distribution per department."""
        rows = self._conn.execute(
            """
            SELECT
                d.department_id,
                d.department_name,
                COUNT(e.employee_id) AS total_employees
            FROM Departments d
            LEFT JOIN Employees e ON d.department_id = e.department_id
            GROUP BY d.department_id, d.department_name
            ORDER BY total_employees DESC, d.department_name ASC;
            """
        ).fetchall()
        results = [
            {
                "department_id": int(row["department_id"]),
                "department_name": str(row["department_name"]),
                "total_employees": int(row["total_employees"]),
            }
            for row in rows
        ]
        logger.info("Computed workforce headcount across %d departments", len(results))
        return results

    def project_duration_metrics(self) -> list[dict[str, Any]]:
        """Calculate project timeline duration in days via SQLite julianday."""
        rows = self._conn.execute(
            """
            SELECT
                p.project_id,
                p.project_name,
                d.department_name,
                p.start_date,
                p.end_date,
                p.budget,
                ROUND(julianday(p.end_date) - julianday(p.start_date), 2) AS duration_days
            FROM Projects p
            JOIN Departments d ON p.department_id = d.department_id
            ORDER BY duration_days DESC, p.project_id ASC;
            """
        ).fetchall()
        results = [
            {
                "project_id": int(row["project_id"]),
                "project_name": str(row["project_name"]),
                "department_name": str(row["department_name"]),
                "start_date": str(row["start_date"]),
                "end_date": str(row["end_date"]),
                "budget": round(float(row["budget"]), 2),
                "duration_days": float(row["duration_days"] or 0.0),
            }
            for row in rows
        ]
        logger.info("Computed project duration metrics for %d projects", len(results))
        return results

    def executive_governance_report(
        self,
        senior_cutoff: str = "2021-01-01",
    ) -> list[dict[str, Any]]:
        """Join projects to senior managers hired prior to ``senior_cutoff``.

        Args:
            senior_cutoff: ISO date (``YYYY-MM-DD``) threshold for senior lead tenure.

        Returns:
            Governance rows pairing department, manager name, project, and budget.
        """
        cutoff = validate_iso_date(senior_cutoff, "senior_cutoff")
        rows = self._conn.execute(
            """
            SELECT
                d.department_name,
                e.employee_id AS manager_id,
                e.first_name || ' ' || e.last_name AS manager_name,
                e.hire_date AS manager_hire_date,
                p.project_id,
                p.project_name,
                p.budget
            FROM Departments d
            JOIN Employees e ON d.department_id = e.department_id
            JOIN Projects p ON d.department_id = p.department_id
            WHERE e.hire_date < ?
            ORDER BY d.department_name ASC, p.project_name ASC, e.employee_id ASC;
            """,
            (cutoff,),
        ).fetchall()
        results = [
            {
                "department_name": str(row["department_name"]),
                "manager_id": int(row["manager_id"]),
                "manager_name": str(row["manager_name"]),
                "manager_hire_date": str(row["manager_hire_date"]),
                "project_id": int(row["project_id"]),
                "project_name": str(row["project_name"]),
                "budget": round(float(row["budget"]), 2),
            }
            for row in rows
        ]
        logger.info(
            "Generated executive governance report (%d rows, cutoff=%s)",
            len(results),
            cutoff,
        )
        return results

    def generate_full_summary(
        self,
        *,
        min_budget: float = 25000.0,
        senior_cutoff: str = "2021-01-01",
    ) -> dict[str, Any]:
        """Generate unified business intelligence snapshot across all modules."""
        budgets = self.department_budget_summary()
        high_value = self.high_value_projects(min_budget=min_budget)
        headcount = self.headcount_by_department()
        durations = self.project_duration_metrics()
        governance = self.executive_governance_report(senior_cutoff=senior_cutoff)

        total_budget = round(sum(item["total_budget"] for item in budgets), 2)
        total_employees = sum(item["total_employees"] for item in headcount)
        total_projects = len(durations)
        avg_duration = (
            round(sum(item["duration_days"] for item in durations) / total_projects, 2)
            if total_projects > 0
            else 0.0
        )

        return {
            "totals": {
                "departments": len(budgets),
                "employees": total_employees,
                "projects": total_projects,
                "total_budget": total_budget,
                "average_project_duration_days": avg_duration,
            },
            "department_budgets": budgets,
            "high_value_projects": high_value,
            "headcount": headcount,
            "project_durations": durations,
            "governance_report": governance,
        }
