"""CLI entrypoint for TechCorp SQL Data Analytics and FastAPI service."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
import json
import logging
from pathlib import Path
import sys
from typing import Any

SRC_DIR = Path(__file__).resolve().parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from techcorp_analytics.analytics import TechCorpAnalytics  # noqa: E402
from techcorp_analytics.api import create_app  # noqa: E402
from techcorp_analytics.config import configure_logging, get_settings  # noqa: E402
from techcorp_analytics.database import (  # noqa: E402
    TechCorpError,
    ValidationError,
    apply_migrations,
    get_connection,
    initialize_database,
    seed_techcorp_data,
    verify_database_health,
)
from techcorp_analytics.repository import TechCorpRepository  # noqa: E402

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    """Create CLI argument parser for health, demo, and API serving modes."""
    parser = argparse.ArgumentParser(
        prog="techcorp-analytics",
        description="TechCorp SQL Data Analytics CLI and FastAPI service.",
    )
    parser.add_argument(
        "--db",
        default=None,
        help="Path to SQLite database (defaults to TECHCORP_DB_PATH).",
    )
    parser.add_argument(
        "--health",
        action="store_true",
        help="Run non-destructive database health and schema verification check.",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Execute end-to-end TechCorp SQL analytics demo in isolated :memory: DB.",
    )
    parser.add_argument(
        "--serve",
        action="store_true",
        help="Launch FastAPI HTTP server via uvicorn.",
    )
    parser.add_argument(
        "--host",
        default=None,
        help="Override API bind host when running --serve.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Override API bind port when running --serve.",
    )
    return parser


def run_health_check(db_path: str, timeout_seconds: float) -> dict[str, Any]:
    """Verify database connectivity and schema without mutating existing DB files.

    Args:
        db_path: Target SQLite database path or ``":memory:"``.
        timeout_seconds: Connection lock timeout in seconds.

    Returns:
        Health report dictionary.
    """
    if db_path == ":memory:":
        with get_connection(":memory:", timeout=timeout_seconds) as conn:
            apply_migrations(conn)
            seed_techcorp_data(conn)
            health = verify_database_health(conn)
    else:
        with get_connection(db_path, read_only=True, timeout=timeout_seconds) as conn:
            health = verify_database_health(conn)

    payload = {
        "status": "healthy" if health["database_ok"] else "degraded",
        "db_path": db_path,
        **health,
    }
    logger.info("Health check passed for db_path=%s counts=%s", db_path, health["counts"])
    return payload


def run_demo() -> dict[str, Any]:
    """Run full TechCorp SQL lifecycle and BI analytics in an isolated :memory: sandbox."""
    with get_connection(":memory:") as conn:
        apply_migrations(conn)
        seeded = seed_techcorp_data(conn)
        repo = TechCorpRepository(conn)
        analytics = TechCorpAnalytics(conn)

        fk_enforced = False
        try:
            repo.add_employee(
                999,
                "Invalid",
                "Dept",
                "invalid.dept@techcorp.com",
                "2024-01-01",
                999,
            )
        except ValidationError:
            fk_enforced = True

        initial_it_staff = repo.get_it_employees()
        budget_update = repo.update_project_budget(201, 60000.0)
        offboarded = repo.offboard_employee(110, raise_if_missing=True)
        summary = analytics.generate_full_summary()

    result = {
        "mode": "sandbox_memory_demo",
        "seeded": seeded,
        "foreign_key_enforced": fk_enforced,
        "it_employees_count": len(initial_it_staff),
        "updated_project": {
            "project_id": budget_update["project_id"],
            "project_name": budget_update["project_name"],
            "previous_budget": budget_update["previous_budget"],
            "budget": budget_update["budget"],
        },
        "offboarded_employee_110": offboarded,
        "summary": summary,
    }
    logger.info(
        "Demo completed: total_budget=%.2f projects=%d employees=%d",
        summary["totals"]["total_budget"],
        summary["totals"]["projects"],
        summary["totals"]["employees"],
    )
    return result


def main(argv: Sequence[str] | None = None) -> int:
    """Parse CLI arguments and dispatch requested operational mode."""
    parser = build_parser()
    args = parser.parse_args(argv)
    settings = get_settings(db_path=args.db)
    configure_logging(settings.log_level)

    if args.health:
        try:
            payload = run_health_check(settings.db_path, settings.request_timeout_seconds)
        except (OSError, TechCorpError) as exc:
            logger.error("Health check failed: %s", exc)
            sys.stdout.write(json.dumps({"status": "unhealthy", "detail": str(exc)}) + "\n")
            return 1
        sys.stdout.write(json.dumps(payload, indent=2) + "\n")
        return 0

    if args.serve:
        import uvicorn

        target_db = Path(settings.db_path)
        if settings.db_path != ":memory:" and not target_db.exists():
            initialize_database(settings.db_path, seed=True, timeout=settings.request_timeout_seconds)
        app = create_app(settings=settings)
        host = args.host or settings.api_host
        port = args.port or settings.api_port
        logger.info("Starting TechCorp API on %s:%d (db=%s)", host, port, settings.db_path)
        uvicorn.run(app, host=host, port=port)
        return 0

    if args.demo or len(sys.argv if argv is None else argv) == 0:
        demo_result = run_demo()
        sys.stdout.write(json.dumps(demo_result, indent=2) + "\n")
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
