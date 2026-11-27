"""Parameterized CRUD repository for TechCorp Departments, Employees, and Projects."""

from __future__ import annotations

from datetime import datetime
import logging
import sqlite3
from typing import Any

from techcorp_analytics.database import ConflictError, NotFoundError, ValidationError

logger = logging.getLogger(__name__)


def _validate_positive_id(value: int, field_name: str) -> int:
    """Ensure integer identifier is strictly positive."""
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValidationError(f"{field_name} must be a positive integer, got {value!r}.")
    return value


def _validate_non_empty_text(value: str, field_name: str) -> str:
    """Ensure string value is non-empty after trimming whitespace."""
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{field_name} must be a non-empty string.")
    return value.strip()


def validate_iso_date(value: str, field_name: str) -> str:
    """Validate YYYY-MM-DD ISO calendar date string."""
    cleaned = _validate_non_empty_text(value, field_name)
    try:
        datetime.strptime(cleaned, "%Y-%m-%d")
    except ValueError as exc:
        raise ValidationError(f"{field_name} must use YYYY-MM-DD format, got {value!r}.") from exc
    return cleaned


def _translate_integrity_error(exc: sqlite3.IntegrityError, context: str) -> TechCorpErrorType:
    """Map SQLite IntegrityError to semantic domain exception."""
    msg = str(exc).lower()
    if "foreign key" in msg:
        return ValidationError(f"{context}: foreign key reference does not exist.")
    if "unique" in msg or "primary key" in msg:
        return ConflictError(f"{context}: conflicting duplicate identifier or unique value.")
    return ValidationError(f"{context}: constraint check failed ({exc}).")


TechCorpErrorType = ValidationError | ConflictError


class TechCorpRepository:
    """Transaction-safe parameterized CRUD operations over TechCorp SQLite schema."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        """Initialize repository with an active SQLite connection.

        Args:
            conn: Active ``sqlite3.Connection`` with ``PRAGMA foreign_keys = ON``.
        """
        self._conn = conn
        self._conn.execute("PRAGMA foreign_keys = ON;")

    def list_departments(self) -> list[dict[str, Any]]:
        """Return all departments ordered by ID."""
        rows = self._conn.execute(
            """
            SELECT department_id, department_name
            FROM Departments
            ORDER BY department_id ASC;
            """
        ).fetchall()
        return [dict(row) for row in rows]

    def add_department(self, department_id: int, department_name: str) -> dict[str, Any]:
        """Insert a new department record inside a transaction.

        Args:
            department_id: Unique positive department ID.
            department_name: Non-empty department name.

        Returns:
            Inserted department record dictionary.
        """
        dept_id = _validate_positive_id(department_id, "department_id")
        dept_name = _validate_non_empty_text(department_name, "department_name")

        try:
            with self._conn:
                self._conn.execute(
                    "INSERT INTO Departments (department_id, department_name) VALUES (?, ?);",
                    (dept_id, dept_name),
                )
        except sqlite3.IntegrityError as exc:
            raise _translate_integrity_error(exc, f"add_department({dept_id})") from exc

        logger.info("Added department id=%d name=%s", dept_id, dept_name)
        return {"department_id": dept_id, "department_name": dept_name}

    def add_employee(
        self,
        employee_id: int,
        first_name: str,
        last_name: str,
        email: str,
        hire_date: str,
        department_id: int,
    ) -> dict[str, Any]:
        """Insert a new employee linked to an existing department."""
        emp_id = _validate_positive_id(employee_id, "employee_id")
        dept_id = _validate_positive_id(department_id, "department_id")
        fname = _validate_non_empty_text(first_name, "first_name")
        lname = _validate_non_empty_text(last_name, "last_name")
        clean_email = _validate_non_empty_text(email, "email").lower()
        if "@" not in clean_email:
            raise ValidationError(f"email must contain '@', got {email!r}.")
        clean_hire_date = validate_iso_date(hire_date, "hire_date")

        try:
            with self._conn:
                self._conn.execute(
                    """
                    INSERT INTO Employees (
                        employee_id, first_name, last_name, email, hire_date, department_id
                    ) VALUES (?, ?, ?, ?, ?, ?);
                    """,
                    (emp_id, fname, lname, clean_email, clean_hire_date, dept_id),
                )
        except sqlite3.IntegrityError as exc:
            raise _translate_integrity_error(exc, f"add_employee({emp_id})") from exc

        logger.info("Added employee id=%d department_id=%d", emp_id, dept_id)
        return self.get_employee(emp_id)

    def add_project(
        self,
        project_id: int,
        project_name: str,
        start_date: str,
        end_date: str,
        budget: float,
        department_id: int,
    ) -> dict[str, Any]:
        """Insert a new project linked to an existing department."""
        proj_id = _validate_positive_id(project_id, "project_id")
        dept_id = _validate_positive_id(department_id, "department_id")
        name = _validate_non_empty_text(project_name, "project_name")
        clean_start = validate_iso_date(start_date, "start_date")
        clean_end = validate_iso_date(end_date, "end_date")
        if clean_end < clean_start:
            raise ValidationError("end_date must be on or after start_date.")
        if budget < 0:
            raise ValidationError(f"budget must be non-negative, got {budget}.")

        try:
            with self._conn:
                self._conn.execute(
                    """
                    INSERT INTO Projects (
                        project_id, project_name, start_date, end_date, budget, department_id
                    ) VALUES (?, ?, ?, ?, ?, ?);
                    """,
                    (proj_id, name, clean_start, clean_end, float(budget), dept_id),
                )
        except sqlite3.IntegrityError as exc:
            raise _translate_integrity_error(exc, f"add_project({proj_id})") from exc

        logger.info("Added project id=%d budget=%.2f department_id=%d", proj_id, budget, dept_id)
        return self.get_project(proj_id)

    def list_employees_with_department(
        self,
        department_name: str | None = None,
    ) -> list[dict[str, Any]]:
        """List employees joined with their department names.

        Args:
            department_name: Optional exact department filter (case-insensitive).

        Returns:
            List of employee dictionaries including ``full_name`` and ``department_name``.
        """
        base_sql = """
            SELECT
                e.employee_id,
                e.first_name,
                e.last_name,
                e.first_name || ' ' || e.last_name AS full_name,
                e.email,
                e.hire_date,
                e.department_id,
                d.department_name
            FROM Employees e
            JOIN Departments d ON e.department_id = d.department_id
        """
        params: tuple[Any, ...] = ()
        if department_name is not None and department_name.strip():
            base_sql += " WHERE LOWER(d.department_name) = LOWER(?)"
            params = (department_name.strip(),)
        base_sql += " ORDER BY d.department_name ASC, e.employee_id ASC;"

        rows = self._conn.execute(base_sql, params).fetchall()
        return [dict(row) for row in rows]

    def get_it_employees(self) -> list[dict[str, Any]]:
        """Retrieve all employees belonging to the IT department."""
        rows = self._conn.execute(
            """
            SELECT
                e.employee_id,
                e.first_name,
                e.last_name,
                e.first_name || ' ' || e.last_name AS full_name,
                e.email,
                e.hire_date,
                e.department_id,
                d.department_name
            FROM Employees e
            JOIN Departments d ON e.department_id = d.department_id
            WHERE d.department_name = ?
            ORDER BY e.employee_id ASC;
            """,
            ("IT",),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_employee(self, employee_id: int) -> dict[str, Any]:
        """Fetch a single employee joined with department metadata."""
        emp_id = _validate_positive_id(employee_id, "employee_id")
        row = self._conn.execute(
            """
            SELECT
                e.employee_id,
                e.first_name,
                e.last_name,
                e.first_name || ' ' || e.last_name AS full_name,
                e.email,
                e.hire_date,
                e.department_id,
                d.department_name
            FROM Employees e
            JOIN Departments d ON e.department_id = d.department_id
            WHERE e.employee_id = ?;
            """,
            (emp_id,),
        ).fetchone()
        if row is None:
            raise NotFoundError(f"Employee with employee_id={emp_id} was not found.")
        return dict(row)

    def list_projects(self) -> list[dict[str, Any]]:
        """List all projects joined with department names."""
        rows = self._conn.execute(
            """
            SELECT
                p.project_id,
                p.project_name,
                p.start_date,
                p.end_date,
                p.budget,
                p.department_id,
                d.department_name
            FROM Projects p
            JOIN Departments d ON p.department_id = d.department_id
            ORDER BY p.project_id ASC;
            """
        ).fetchall()
        return [dict(row) for row in rows]

    def get_project(self, project_id: int) -> dict[str, Any]:
        """Fetch a single project by ID or raise ``NotFoundError``."""
        proj_id = _validate_positive_id(project_id, "project_id")
        row = self._conn.execute(
            """
            SELECT
                p.project_id,
                p.project_name,
                p.start_date,
                p.end_date,
                p.budget,
                p.department_id,
                d.department_name
            FROM Projects p
            JOIN Departments d ON p.department_id = d.department_id
            WHERE p.project_id = ?;
            """,
            (proj_id,),
        ).fetchone()
        if row is None:
            raise NotFoundError(f"Project with project_id={proj_id} was not found.")
        return dict(row)

    def update_project_budget(self, project_id: int, new_budget: float) -> dict[str, Any]:
        """Update a project's budget transactionally after validation.

        Args:
            project_id: Target project ID.
            new_budget: New non-negative budget amount in USD.

        Returns:
            Updated project dictionary including ``previous_budget``.

        Raises:
            ValidationError: If ``project_id <= 0`` or ``new_budget < 0``.
            NotFoundError: If ``project_id`` does not exist.
        """
        proj_id = _validate_positive_id(project_id, "project_id")
        if new_budget < 0:
            raise ValidationError(f"Project budget must be >= 0, got {new_budget}.")

        existing = self.get_project(proj_id)
        previous_budget = float(existing["budget"])

        with self._conn:
            cursor = self._conn.execute(
                "UPDATE Projects SET budget = ? WHERE project_id = ?;",
                (float(new_budget), proj_id),
            )
            if cursor.rowcount == 0:
                raise NotFoundError(f"Project with project_id={proj_id} was not found.")

        updated = self.get_project(proj_id)
        updated["previous_budget"] = previous_budget
        logger.info(
            "Updated project id=%d budget from %.2f to %.2f",
            proj_id,
            previous_budget,
            new_budget,
        )
        return updated

    def offboard_employee(
        self,
        employee_id: int,
        *,
        raise_if_missing: bool = False,
    ) -> bool:
        """Delete an employee record from the database cleanly.

        Args:
            employee_id: Employee ID to remove.
            raise_if_missing: If True, raises ``NotFoundError`` when no row matches.

        Returns:
            True if a row was deleted, False if missing and ``raise_if_missing=False``.

        Raises:
            ValidationError: If ``employee_id <= 0``.
            NotFoundError: If missing and ``raise_if_missing=True``.
        """
        emp_id = _validate_positive_id(employee_id, "employee_id")
        with self._conn:
            cursor = self._conn.execute(
                "DELETE FROM Employees WHERE employee_id = ?;",
                (emp_id,),
            )
            deleted = cursor.rowcount > 0

        if not deleted:
            if raise_if_missing:
                raise NotFoundError(f"Employee with employee_id={emp_id} was not found.")
            logger.warning("Offboard requested for non-existent employee_id=%d", emp_id)
            return False

        logger.info("Offboarded employee_id=%d successfully", emp_id)
        return True
