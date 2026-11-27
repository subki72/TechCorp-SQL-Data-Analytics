"""SQLite connection management, schema migrations, and deterministic seeding."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
import logging
from pathlib import Path
import sqlite3
from typing import Any

from techcorp_analytics.config import DEFAULT_MIGRATIONS_DIR

logger = logging.getLogger(__name__)

REQUIRED_TABLES = ("Departments", "Employees", "Projects")

SEED_DEPARTMENTS: tuple[tuple[int, str], ...] = (
    (1, "Human Resources"),
    (2, "IT"),
    (3, "Marketing"),
    (4, "Finance"),
    (5, "Sales"),
)

SEED_EMPLOYEES: tuple[tuple[int, str, str, str, str, int], ...] = (
    (101, "John", "Doe", "john.doe@techcorp.com", "2022-01-15", 2),
    (102, "Jane", "Smith", "jane.smith@techcorp.com", "2021-05-20", 1),
    (103, "Emily", "Johnson", "emily.j@techcorp.com", "2023-03-10", 3),
    (104, "Michael", "Brown", "michael.b@techcorp.com", "2020-11-01", 2),
    (105, "Sarah", "Davis", "sarah.davis@techcorp.com", "2022-07-23", 4),
    (106, "David", "Wilson", "david.wilson@techcorp.com", "2021-09-14", 5),
    (107, "Laura", "Martinez", "laura.m@techcorp.com", "2023-01-05", 2),
    (108, "James", "Taylor", "james.t@techcorp.com", "2020-04-18", 1),
    (109, "Olivia", "Anderson", "olivia.a@techcorp.com", "2022-12-01", 3),
    (110, "Robert", "Thomas", "robert.t@techcorp.com", "2021-06-30", 4),
)

SEED_PROJECTS: tuple[tuple[int, str, str, str, float, int], ...] = (
    (201, "Website Redesign", "2023-01-01", "2023-06-30", 50000.0, 2),
    (202, "Employee Onboarding", "2023-02-15", "2023-04-30", 10000.0, 1),
    (203, "Market Research", "2023-03-01", "2023-08-31", 25000.0, 3),
    (204, "Financial Audit", "2023-04-01", "2023-05-31", 15000.0, 4),
    (205, "Sales Strategy", "2023-05-01", "2023-11-30", 30000.0, 5),
    (206, "App Development", "2023-06-01", "2023-12-31", 80000.0, 2),
)


class TechCorpError(Exception):
    """Base domain exception for TechCorp Analytics."""


class ValidationError(TechCorpError):
    """Raised when caller input violates domain or constraint rules."""


class NotFoundError(TechCorpError):
    """Raised when a requested entity does not exist."""


class ConflictError(TechCorpError):
    """Raised when an operation conflicts with uniqueness or referential state."""


def _connect_sqlite(raw_path: str, *, read_only: bool, timeout: float) -> sqlite3.Connection:
    """Create raw sqlite3 connection in read-only URI or read-write mode."""
    if read_only:
        if raw_path == ":memory:":
            raise ValidationError("Read-only mode is not supported for ':memory:' databases.")
        resolved = Path(raw_path).resolve()
        if not resolved.exists():
            raise FileNotFoundError(f"Database file not found: {resolved}")
        return sqlite3.connect(
            f"{resolved.as_uri()}?mode=ro",
            uri=True,
            timeout=timeout,
            check_same_thread=False,
        )
    if raw_path != ":memory:":
        Path(raw_path).parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(raw_path, timeout=timeout, check_same_thread=False)


def open_connection(
    db_path: str | Path,
    *,
    read_only: bool = False,
    timeout: float = 10.0,
) -> sqlite3.Connection:
    """Open a SQLite connection with ``PRAGMA foreign_keys = ON`` enforced.

    Args:
        db_path: SQLite database file path or ``":memory:"``.
        read_only: Whether to open an existing file database in read-only URI mode.
        timeout: Lock wait timeout in seconds.

    Returns:
        Configured ``sqlite3.Connection`` with ``sqlite3.Row`` row factory.
    """
    if timeout <= 0:
        raise ValidationError(f"SQLite connection timeout must be positive, got {timeout}.")

    conn = _connect_sqlite(str(db_path), read_only=read_only, timeout=timeout)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    fk_row = conn.execute("PRAGMA foreign_keys;").fetchone()
    if fk_row is None or int(fk_row[0]) != 1:
        logger.warning("SQLite foreign_keys pragma did not report enabled state.")
    return conn


@contextmanager
def get_connection(
    db_path: str | Path,
    *,
    read_only: bool = False,
    timeout: float = 10.0,
) -> Iterator[sqlite3.Connection]:
    """Context manager wrapping SQLite connection lifecycle and transaction safety.

    Args:
        db_path: SQLite database file path or ``":memory:"``.
        read_only: Open database in read-only mode when True.
        timeout: Lock wait timeout in seconds.

    Yields:
        Active ``sqlite3.Connection``.
    """
    conn = open_connection(db_path, read_only=read_only, timeout=timeout)
    try:
        yield conn
        if not read_only:
            conn.commit()
    except Exception:
        if not read_only:
            conn.rollback()
        raise
    finally:
        conn.close()


def apply_migrations(
    conn: sqlite3.Connection,
    migrations_dir: Path | None = None,
) -> list[str]:
    """Apply sorted SQL migration scripts idempotently to an open connection.

    Args:
        conn: Open SQLite connection.
        migrations_dir: Directory containing ``*.sql`` migration scripts.

    Returns:
        List of executed migration filenames in execution order.

    Raises:
        FileNotFoundError: If ``migrations_dir`` does not exist or has no ``.sql`` files.
    """
    target_dir = migrations_dir or DEFAULT_MIGRATIONS_DIR
    if not target_dir.is_dir():
        raise FileNotFoundError(f"Migrations directory does not exist: {target_dir}")

    sql_files = sorted(target_dir.glob("*.sql"))
    if not sql_files:
        raise FileNotFoundError(f"No .sql migration files found in: {target_dir}")

    applied: list[str] = []
    for sql_file in sql_files:
        sql_script = sql_file.read_text(encoding="utf-8")
        conn.executescript(sql_script)
        conn.execute("PRAGMA foreign_keys = ON;")
        applied.append(sql_file.name)
        logger.info("Applied SQL migration %s", sql_file.name)
    return applied


def _insert_seed_batches(conn: sqlite3.Connection) -> None:
    """Insert deterministic seed rows idempotently across all TechCorp tables."""
    conn.executemany(
        "INSERT OR IGNORE INTO Departments (department_id, department_name) VALUES (?, ?);",
        SEED_DEPARTMENTS,
    )
    conn.executemany(
        """
        INSERT OR IGNORE INTO Employees (
            employee_id, first_name, last_name, email, hire_date, department_id
        ) VALUES (?, ?, ?, ?, ?, ?);
        """,
        SEED_EMPLOYEES,
    )
    conn.executemany(
        """
        INSERT OR IGNORE INTO Projects (
            project_id, project_name, start_date, end_date, budget, department_id
        ) VALUES (?, ?, ?, ?, ?, ?);
        """,
        SEED_PROJECTS,
    )


def seed_techcorp_data(
    conn: sqlite3.Connection,
    *,
    reset_existing: bool = False,
) -> dict[str, int]:
    """Populate TechCorp tables idempotently with deterministic sample records."""
    conn.execute("PRAGMA foreign_keys = ON;")
    with conn:
        if reset_existing:
            conn.execute("DELETE FROM Projects;")
            conn.execute("DELETE FROM Employees;")
            conn.execute("DELETE FROM Departments;")

        before = {tbl: _count_rows(conn, tbl) for tbl in REQUIRED_TABLES}
        _insert_seed_batches(conn)

    inserted = {tbl.lower(): _count_rows(conn, tbl) - before[tbl] for tbl in REQUIRED_TABLES}
    logger.info(
        "Seeded TechCorp database (departments=+%d, employees=+%d, projects=+%d)",
        inserted["departments"],
        inserted["employees"],
        inserted["projects"],
    )
    return inserted


def initialize_database(
    db_path: str | Path,
    *,
    seed: bool = True,
    migrations_dir: Path | None = None,
    timeout: float = 10.0,
) -> dict[str, int]:
    """Create/migrate database at ``db_path`` and optionally seed sample data.

    Args:
        db_path: Target SQLite database path.
        seed: Whether to populate initial TechCorp rows idempotently.
        migrations_dir: Optional custom migrations directory.
        timeout: SQLite lock timeout in seconds.

    Returns:
        Dictionary of inserted row counts (zeros if ``seed=False`` or already populated).
    """
    with get_connection(db_path, timeout=timeout) as conn:
        apply_migrations(conn, migrations_dir=migrations_dir)
        if seed:
            return seed_techcorp_data(conn)
        return {"departments": 0, "employees": 0, "projects": 0}


def verify_database_health(conn: sqlite3.Connection) -> dict[str, Any]:
    """Verify schema presence, foreign key enforcement, and current row counts.

    Args:
        conn: Open SQLite connection.

    Returns:
        Dictionary describing health status, foreign key pragma, and table row counts.

    Raises:
        TechCorpError: If required tables are missing from the database schema.
    """
    fk_row = conn.execute("PRAGMA foreign_keys;").fetchone()
    fk_enabled = bool(fk_row and int(fk_row[0]) == 1)

    table_rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table';").fetchall()
    existing_tables = {str(row["name"]) for row in table_rows}
    missing = [tbl for tbl in REQUIRED_TABLES if tbl not in existing_tables]
    if missing:
        raise TechCorpError(f"Missing required database tables: {', '.join(missing)}")

    counts = {tbl.lower(): _count_rows(conn, tbl) for tbl in REQUIRED_TABLES}
    return {
        "database_ok": True,
        "foreign_keys_enabled": fk_enabled,
        "tables": list(REQUIRED_TABLES),
        "counts": counts,
    }


def _count_rows(conn: sqlite3.Connection, table_name: str) -> int:
    """Count rows for an allowlisted TechCorp table name."""
    if table_name not in REQUIRED_TABLES:
        raise ValidationError(f"Unsupported table name: {table_name}")
    row = conn.execute(f"SELECT COUNT(*) AS cnt FROM {table_name};").fetchone()
    return int(row["cnt"]) if row is not None else 0
