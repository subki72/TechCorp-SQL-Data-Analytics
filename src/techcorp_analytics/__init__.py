"""TechCorp SQL Data Analytics package."""

from __future__ import annotations

from techcorp_analytics.config import Settings, configure_logging, get_settings
from techcorp_analytics.database import (
    ConflictError,
    NotFoundError,
    TechCorpError,
    ValidationError,
    apply_migrations,
    get_connection,
    initialize_database,
    open_connection,
    seed_techcorp_data,
    verify_database_health,
)

__version__ = "1.0.0"

__all__ = [
    "ConflictError",
    "NotFoundError",
    "Settings",
    "TechCorpError",
    "ValidationError",
    "__version__",
    "apply_migrations",
    "configure_logging",
    "get_connection",
    "get_settings",
    "initialize_database",
    "open_connection",
    "seed_techcorp_data",
    "verify_database_health",
]
