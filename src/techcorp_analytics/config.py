"""Externalized configuration and logging setup for TechCorp Analytics."""

from __future__ import annotations

from dataclasses import dataclass
import logging
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MIGRATIONS_DIR = PROJECT_ROOT / "migrations"
DEFAULT_DB_PATH = "techcorp_db.sqlite"

_VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


def _parse_int_env(name: str, default: int, *, minimum: int = 1) -> int:
    """Parse an integer environment variable with validation."""
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        parsed = int(raw.strip())
    except ValueError as exc:
        raise ValueError(f"Environment variable {name} must be an integer, got {raw!r}.") from exc
    if parsed < minimum:
        raise ValueError(f"Environment variable {name} must be >= {minimum}, got {parsed}.")
    return parsed


def _parse_float_env(name: str, default: float, *, minimum: float = 0.0) -> float:
    """Parse a float environment variable with validation."""
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        parsed = float(raw.strip())
    except ValueError as exc:
        raise ValueError(f"Environment variable {name} must be a number, got {raw!r}.") from exc
    if parsed < minimum:
        raise ValueError(f"Environment variable {name} must be >= {minimum}, got {parsed}.")
    return parsed


@dataclass(frozen=True)
class Settings:
    """Immutable application settings loaded from environment variables."""

    db_path: str = DEFAULT_DB_PATH
    log_level: str = "INFO"
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    cors_origins: tuple[str, ...] = ("http://localhost:3000", "http://127.0.0.1:8000")
    request_timeout_seconds: float = 10.0
    senior_cutoff_date: str = "2021-01-01"
    cache_ttl_seconds: float = 60.0
    rate_limit_requests: int = 120
    rate_limit_window_seconds: float = 60.0


def get_settings(db_path: str | None = None) -> Settings:
    """Load application settings from environment variables with optional DB override.

    Args:
        db_path: Optional database path overriding ``TECHCORP_DB_PATH``.

    Returns:
        Validated ``Settings`` instance.
    """
    resolved_db = (
        db_path
        if db_path is not None
        else (os.getenv("TECHCORP_DB_PATH", DEFAULT_DB_PATH).strip() or DEFAULT_DB_PATH)
    )
    raw_level = os.getenv("TECHCORP_LOG_LEVEL", "INFO").strip().upper() or "INFO"
    log_level = raw_level if raw_level in _VALID_LOG_LEVELS else "INFO"

    raw_origins = os.getenv(
        "TECHCORP_CORS_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:8000",
    )
    cors_origins = tuple(item.strip() for item in raw_origins.split(",") if item.strip())
    if not cors_origins:
        cors_origins = ("http://localhost:3000",)

    return Settings(
        db_path=resolved_db,
        log_level=log_level,
        api_host=os.getenv("TECHCORP_API_HOST", "127.0.0.1").strip() or "127.0.0.1",
        api_port=_parse_int_env("TECHCORP_API_PORT", 8000, minimum=1),
        cors_origins=cors_origins,
        request_timeout_seconds=_parse_float_env(
            "TECHCORP_REQUEST_TIMEOUT_SECONDS", 10.0, minimum=0.1
        ),
        senior_cutoff_date=(
            os.getenv("TECHCORP_SENIOR_CUTOFF_DATE", "2021-01-01").strip() or "2021-01-01"
        ),
        cache_ttl_seconds=_parse_float_env("TECHCORP_CACHE_TTL_SECONDS", 60.0, minimum=0.0),
        rate_limit_requests=_parse_int_env("TECHCORP_RATE_LIMIT_REQUESTS", 120, minimum=1),
        rate_limit_window_seconds=_parse_float_env(
            "TECHCORP_RATE_LIMIT_WINDOW_SECONDS", 60.0, minimum=1.0
        ),
    )


def configure_logging(level: str = "INFO") -> None:
    """Configure root structured logging format if not already configured.

    Args:
        level: Logging level name (e.g. ``INFO``, ``DEBUG``).
    """
    normalized = level.strip().upper()
    numeric_level = getattr(logging, normalized, logging.INFO)
    root_logger = logging.getLogger()
    if not root_logger.handlers:
        logging.basicConfig(
            level=numeric_level,
            format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        )
    else:
        root_logger.setLevel(numeric_level)
