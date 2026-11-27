"""Unit tests for SQLite connection management, migrations, FK enforcement, and seeding."""

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
    TechCorpError,
    ValidationError,
    apply_migrations,
    get_connection,
    initialize_database,
    open_connection,
    seed_techcorp_data,
    verify_database_health,
)


def test_initialize_database_enforces_foreign_keys_and_seeds(tmp_path: Path) -> None:
    """Initializing a fresh DB applies schema, activates foreign keys, and seeds idempotently."""
    db_file = tmp_path / "techcorp_test.sqlite"

    first_insert = initialize_database(db_file, seed=True)
    second_insert = initialize_database(db_file, seed=True)

    assert first_insert == {"departments": 5, "employees": 10, "projects": 6}
    assert second_insert == {"departments": 0, "employees": 0, "projects": 0}

    with get_connection(db_file, read_only=True) as conn:
        health = verify_database_health(conn)
        assert health["database_ok"] is True
        assert health["foreign_keys_enabled"] is True
        assert health["counts"] == {"departments": 5, "employees": 10, "projects": 6}


def test_foreign_key_constraint_rejects_invalid_department(tmp_path: Path) -> None:
    """PRAGMA foreign_keys=ON prevents inserting employees or projects for unknown departments."""
    db_file = tmp_path / "fk_test.sqlite"
    initialize_database(db_file, seed=True)

    with get_connection(db_file) as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO Employees (
                    employee_id, first_name, last_name, email, hire_date, department_id
                ) VALUES (999, 'Ghost', 'User', 'ghost@techcorp.com', '2024-01-01', 999);
                """
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO Projects (
                    project_id, project_name, start_date, end_date, budget, department_id
                ) VALUES (999, 'Orphan Project', '2024-01-01', '2024-02-01', 1000.0, 999);
                """
            )


def test_negative_budget_rejected_by_check_constraint(tmp_path: Path) -> None:
    """Schema CHECK constraint prevents negative project budgets at the database layer."""
    db_file = tmp_path / "check_budget.sqlite"
    initialize_database(db_file, seed=True)

    with get_connection(db_file) as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO Projects (
                    project_id, project_name, start_date, end_date, budget, department_id
                ) VALUES (301, 'Invalid Budget', '2024-01-01', '2024-02-01', -50.0, 2);
                """
            )


def test_seed_reset_existing_restores_clean_state(tmp_path: Path) -> None:
    """Passing reset_existing=True clears modified rows and restores seed records."""
    db_file = tmp_path / "reset_seed.sqlite"
    initialize_database(db_file, seed=True)

    with get_connection(db_file) as conn:
        conn.execute("DELETE FROM Employees WHERE employee_id = 110;")
        assert verify_database_health(conn)["counts"]["employees"] == 9
        inserted = seed_techcorp_data(conn, reset_existing=True)
        assert inserted == {"departments": 5, "employees": 10, "projects": 6}


def test_read_only_connection_against_committed_snapshot() -> None:
    """Committed techcorp_db.sqlite passes read-only health verification without mutation."""
    snapshot_db = ROOT_DIR / "techcorp_db.sqlite"
    if not snapshot_db.exists():
        pytest.skip("Committed snapshot database not present")

    with get_connection(snapshot_db, read_only=True) as conn:
        health = verify_database_health(conn)
        assert health["database_ok"] is True
        assert health["foreign_keys_enabled"] is True
        assert health["counts"]["departments"] == 5
        assert health["counts"]["projects"] == 6
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("DELETE FROM Employees WHERE employee_id = 101;")


def test_open_connection_and_migration_error_guards(tmp_path: Path) -> None:
    """Invalid connection parameters and missing migrations raise explicit errors."""
    with pytest.raises(ValidationError):
        open_connection(":memory:", timeout=0)

    with pytest.raises(ValidationError):
        open_connection(":memory:", read_only=True)

    with pytest.raises(FileNotFoundError):
        open_connection(tmp_path / "missing.sqlite", read_only=True)

    empty_migrations = tmp_path / "empty_migrations"
    empty_migrations.mkdir()
    with get_connection(":memory:") as conn:
        with pytest.raises(FileNotFoundError):
            apply_migrations(conn, migrations_dir=tmp_path / "does_not_exist")
        with pytest.raises(FileNotFoundError):
            apply_migrations(conn, migrations_dir=empty_migrations)


def test_get_connection_rolls_back_uncommitted_changes_on_error(tmp_path: Path) -> None:
    """Context manager rolls back open transaction when an exception propagates."""
    db_file = tmp_path / "rollback.sqlite"
    initialize_database(db_file, seed=True)

    with pytest.raises(RuntimeError, match="boom"):
        with get_connection(db_file) as conn:
            conn.execute(
                "INSERT INTO Departments (department_id, department_name) VALUES (99, 'Temp');"
            )
            raise RuntimeError("boom")

    with get_connection(db_file, read_only=True) as conn:
        row = conn.execute("SELECT * FROM Departments WHERE department_id = 99;").fetchone()
        assert row is None


def test_verify_database_health_fails_on_unmigrated_db() -> None:
    """Empty SQLite database without TechCorp tables raises TechCorpError."""
    with get_connection(":memory:") as conn:
        with pytest.raises(TechCorpError, match="Missing required database tables"):
            verify_database_health(conn)
