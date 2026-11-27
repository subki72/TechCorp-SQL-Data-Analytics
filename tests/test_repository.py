"""Unit tests for parameterized TechCorp CRUD repository operations."""

from __future__ import annotations

from pathlib import Path
import sqlite3
import sys

import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from techcorp_analytics.database import (  # noqa: E402
    ConflictError,
    NotFoundError,
    ValidationError,
    apply_migrations,
    get_connection,
    seed_techcorp_data,
)
from techcorp_analytics.repository import TechCorpRepository  # noqa: E402


def _seeded_memory_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    apply_migrations(conn)
    seed_techcorp_data(conn)
    return conn


def test_add_department_happy_and_error_paths() -> None:
    """Adding a department succeeds cleanly while invalid IDs and duplicates raise errors."""
    conn = _seeded_memory_conn()
    try:
        repo = TechCorpRepository(conn)
        created = repo.add_department(6, "Security")
        assert created == {"department_id": 6, "department_name": "Security"}
        assert len(repo.list_departments()) == 6

        with pytest.raises(ConflictError):
            repo.add_department(6, "Security Duplicate")

        with pytest.raises(ValidationError):
            repo.add_department(0, "Invalid")

        with pytest.raises(ValidationError):
            repo.add_department(7, "   ")
    finally:
        conn.close()


def test_add_employee_validates_fk_email_and_dates() -> None:
    """Adding employees enforces FK existence, valid email, ISO dates, and uniqueness."""
    conn = _seeded_memory_conn()
    try:
        repo = TechCorpRepository(conn)
        created = repo.add_employee(
            111,
            "Grace",
            "Hopper",
            "Grace.Hopper@TechCorp.com",
            "2024-02-15",
            2,
        )
        assert created["email"] == "grace.hopper@techcorp.com"
        assert created["department_name"] == "IT"

        with pytest.raises(ValidationError, match="foreign key"):
            repo.add_employee(112, "No", "Dept", "nodept@techcorp.com", "2024-02-15", 999)

        with pytest.raises(ConflictError):
            repo.add_employee(113, "Dup", "Mail", "grace.hopper@techcorp.com", "2024-02-15", 2)

        with pytest.raises(ValidationError, match="email"):
            repo.add_employee(114, "Bad", "Mail", "invalid-email", "2024-02-15", 2)

        with pytest.raises(ValidationError, match="YYYY-MM-DD"):
            repo.add_employee(115, "Bad", "Date", "bad.date@techcorp.com", "15-02-2024", 2)
    finally:
        conn.close()


def test_add_project_validation_and_listing() -> None:
    """Adding projects validates date ordering, non-negative budget, and FK integrity."""
    conn = _seeded_memory_conn()
    try:
        repo = TechCorpRepository(conn)
        project = repo.add_project(207, "Data Lake", "2024-01-01", "2024-06-30", 75000.0, 2)
        assert project["project_name"] == "Data Lake"
        assert len(repo.list_projects()) == 7

        with pytest.raises(ValidationError, match="end_date"):
            repo.add_project(208, "Bad Dates", "2024-06-30", "2024-01-01", 5000.0, 2)

        with pytest.raises(ValidationError, match="budget"):
            repo.add_project(209, "Neg Budget", "2024-01-01", "2024-02-01", -1.0, 2)

        with pytest.raises(ValidationError, match="foreign key"):
            repo.add_project(210, "Missing Dept", "2024-01-01", "2024-02-01", 1000.0, 888)
    finally:
        conn.close()


def test_list_employees_with_department_and_it_filter() -> None:
    """Employee directory queries return joined department metadata and accurate IT filters."""
    conn = _seeded_memory_conn()
    try:
        repo = TechCorpRepository(conn)
        all_employees = repo.list_employees_with_department()
        assert len(all_employees) == 10

        it_filtered = repo.list_employees_with_department(department_name="it")
        it_staff = repo.get_it_employees()
        assert len(it_filtered) == 3
        assert [row["full_name"] for row in it_staff] == [
            "John Doe",
            "Michael Brown",
            "Laura Martinez",
        ]
    finally:
        conn.close()


def test_update_project_budget_happy_and_error_paths(tmp_path: Path) -> None:
    """Budget update mutates target project transactionally and handles invalid/missing cases."""
    db_file = tmp_path / "repo_budget.sqlite"
    with get_connection(db_file) as conn:
        apply_migrations(conn)
        seed_techcorp_data(conn)
        repo = TechCorpRepository(conn)

        updated = repo.update_project_budget(201, 60000.0)
        assert updated["previous_budget"] == 50000.0
        assert updated["budget"] == 60000.0

        with pytest.raises(ValidationError):
            repo.update_project_budget(201, -500.0)

        with pytest.raises(NotFoundError):
            repo.update_project_budget(999, 10000.0)


def test_offboard_employee_happy_and_missing_paths() -> None:
    """Offboarding removes target employee cleanly and reports missing records accurately."""
    conn = _seeded_memory_conn()
    try:
        repo = TechCorpRepository(conn)
        assert repo.offboard_employee(110) is True
        assert repo.offboard_employee(110) is False

        with pytest.raises(NotFoundError):
            repo.offboard_employee(110, raise_if_missing=True)

        with pytest.raises(NotFoundError):
            repo.get_employee(110)
    finally:
        conn.close()
