"""TechCorp SQL Data Analytics package."""

from __future__ import annotations

from techcorp_analytics.analytics import AnalyticsCache, TechCorpAnalytics
from techcorp_analytics.api import InMemoryRateLimiter, create_app
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
from techcorp_analytics.repository import TechCorpRepository

__version__ = "1.0.0"

__all__ = [
    "AnalyticsCache",
    "ConflictError",
    "InMemoryRateLimiter",
    "NotFoundError",
    "Settings",
    "TechCorpAnalytics",
    "TechCorpError",
    "TechCorpRepository",
    "ValidationError",
    "__version__",
    "apply_migrations",
    "configure_logging",
    "create_app",
    "get_connection",
    "get_settings",
    "initialize_database",
    "open_connection",
    "seed_techcorp_data",
    "verify_database_health",
]
