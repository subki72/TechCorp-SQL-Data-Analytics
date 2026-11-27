"""FastAPI service exposing TechCorp SQL analytics and lifecycle endpoints."""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Iterator
import logging
import sqlite3
import threading
import time
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from techcorp_analytics.analytics import AnalyticsCache, TechCorpAnalytics
from techcorp_analytics.config import Settings, configure_logging, get_settings
from techcorp_analytics.database import (
    ConflictError,
    NotFoundError,
    TechCorpError,
    ValidationError,
    get_connection,
    verify_database_health,
)
from techcorp_analytics.repository import TechCorpRepository

logger = logging.getLogger(__name__)


class InMemoryRateLimiter:
    """Sliding-window in-memory rate limiter keyed by client host."""

    def __init__(self, max_requests: int = 120, window_seconds: float = 60.0) -> None:
        """Configure maximum request allowance per sliding time window."""
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._lock = threading.Lock()
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, client_key: str) -> bool:
        """Record a request for ``client_key`` and return True if permitted."""
        now = time.monotonic()
        cutoff = now - self._window_seconds
        with self._lock:
            bucket = self._hits[client_key]
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if len(bucket) >= self._max_requests:
                return False
            bucket.append(now)
            return True

    def reset(self) -> None:
        """Clear all tracked client timestamps."""
        with self._lock:
            self._hits.clear()


class HealthResponse(BaseModel):
    """Schema for service and SQLite readiness probes."""

    status: str
    service: str
    version: str
    database_ok: bool
    foreign_keys_enabled: bool
    counts: dict[str, int]


class DepartmentBudgetItem(BaseModel):
    """Department budget summary schema."""

    department_id: int
    department_name: str
    total_projects: int
    total_budget: float
    average_budget: float


class HeadcountItem(BaseModel):
    """Department workforce headcount schema."""

    department_id: int
    department_name: str
    total_employees: int


class ProjectDurationItem(BaseModel):
    """Project timeline duration metric schema."""

    project_id: int
    project_name: str
    department_name: str
    start_date: str
    end_date: str
    budget: float
    duration_days: float


class HighValueProjectItem(BaseModel):
    """High-value project record schema."""

    project_id: int
    project_name: str
    budget: float
    start_date: str
    end_date: str
    department_name: str


class GovernanceItem(BaseModel):
    """Executive project governance mapping schema."""

    department_name: str
    manager_id: int
    manager_name: str
    manager_hire_date: str
    project_id: int
    project_name: str
    budget: float


class EmployeeItem(BaseModel):
    """Employee with department mapping schema."""

    employee_id: int
    first_name: str
    last_name: str
    full_name: str
    email: str | None
    hire_date: str
    department_id: int
    department_name: str


class AnalyticsTotals(BaseModel):
    """Aggregate KPI totals for TechCorp."""

    departments: int
    employees: int
    projects: int
    total_budget: float
    average_project_duration_days: float


class AnalyticsSummaryResponse(BaseModel):
    """Consolidated response schema for ``GET /analyze``."""

    totals: AnalyticsTotals
    department_budgets: list[DepartmentBudgetItem]
    high_value_projects: list[HighValueProjectItem]
    headcount: list[HeadcountItem]
    project_durations: list[ProjectDurationItem]
    governance_report: list[GovernanceItem]


class BudgetUpdateRequest(BaseModel):
    """Request payload for updating a project's budget."""

    budget: float = Field(ge=0.0, description="Non-negative project budget in USD.")


class BudgetUpdateResponse(BaseModel):
    """Response payload confirming budget update."""

    project_id: int
    project_name: str
    previous_budget: float
    budget: float
    department_name: str


class OffboardResponse(BaseModel):
    """Response payload confirming employee offboarding."""

    employee_id: int
    offboarded: bool


def _get_db_connection(request: Request) -> Iterator[sqlite3.Connection]:
    """Yield a managed SQLite connection from application state."""
    cfg: Settings = request.app.state.settings
    read_only: bool = bool(request.app.state.read_only)
    with get_connection(
        cfg.db_path,
        read_only=read_only,
        timeout=cfg.request_timeout_seconds,
    ) as conn:
        yield conn


def _enforce_rate_limit(request: Request) -> None:
    """Enforce per-client sliding-window request rate limit."""
    limiter: InMemoryRateLimiter = request.app.state.rate_limiter
    client_host = request.client.host if request.client else "unknown"
    if not limiter.check(client_host):
        logger.warning("Rate limit exceeded for client=%s", client_host)
        raise RateLimitExceededError("Too many requests; please retry shortly.")


class RateLimitExceededError(TechCorpError):
    """Raised when an HTTP client exceeds the configured request rate limit."""


DbDep = Annotated[sqlite3.Connection, Depends(_get_db_connection)]
RateLimitDep = Annotated[None, Depends(_enforce_rate_limit)]


def _register_exception_handlers(app: FastAPI) -> None:
    """Attach centralized JSON exception handlers without exposing stack traces."""

    @app.exception_handler(RateLimitExceededError)
    async def _rate_limit_handler(
        _request: Request,
        exc: RateLimitExceededError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={"detail": str(exc)},
        )

    @app.exception_handler(ValidationError)
    async def _validation_handler(_request: Request, exc: ValidationError) -> JSONResponse:
        logger.warning("Domain validation error: %s", exc)
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={"detail": str(exc)},
        )

    @app.exception_handler(NotFoundError)
    async def _not_found_handler(_request: Request, exc: NotFoundError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": str(exc)},
        )

    @app.exception_handler(ConflictError)
    async def _conflict_handler(_request: Request, exc: ConflictError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"detail": str(exc)},
        )

    @app.exception_handler(TechCorpError)
    async def _domain_handler(_request: Request, exc: TechCorpError) -> JSONResponse:
        logger.error("TechCorp domain error: %s", exc)
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": str(exc)},
        )

    @app.exception_handler(Exception)
    async def _unhandled_handler(_request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled API exception: %s", exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Internal server error."},
        )


def _register_routes(app: FastAPI) -> None:
    """Register REST endpoints delegating all SQL to analytics and repository layers."""

    @app.get("/health", response_model=HealthResponse, tags=["Operations"])
    def health_check(conn: DbDep, _: RateLimitDep) -> dict[str, Any]:
        """Liveness and SQLite readiness check endpoint."""
        health = verify_database_health(conn)
        return {
            "status": "healthy" if health["database_ok"] else "degraded",
            "service": "techcorp-analytics-api",
            "version": "1.0.0",
            **health,
        }

    @app.get("/analyze", response_model=AnalyticsSummaryResponse, tags=["Analytics"])
    def analyze(
        request: Request,
        conn: DbDep,
        _: RateLimitDep,
        min_budget: float = Query(default=25000.0, ge=0.0),
        senior_cutoff: str | None = Query(default=None),
    ) -> dict[str, Any]:
        """Run full TechCorp BI analysis with TTL caching."""
        cfg: Settings = request.app.state.settings
        cutoff = senior_cutoff or cfg.senior_cutoff_date
        cache_key = f"analyze:{min_budget}:{cutoff}"
        cache: AnalyticsCache = request.app.state.cache
        cached = cache.get(cache_key)
        if cached is not None:
            return dict(cached)

        analytics = TechCorpAnalytics(conn)
        summary = analytics.generate_full_summary(
            min_budget=min_budget,
            senior_cutoff=cutoff,
        )
        cache.set(cache_key, summary)
        return summary

    @app.get(
        "/departments/budgets",
        response_model=list[DepartmentBudgetItem],
        tags=["Analytics"],
    )
    def department_budgets(conn: DbDep, _: RateLimitDep) -> list[dict[str, Any]]:
        """Retrieve budget allocations grouped by department."""
        return TechCorpAnalytics(conn).department_budget_summary()

    @app.get(
        "/departments/headcount",
        response_model=list[HeadcountItem],
        tags=["Analytics"],
    )
    def department_headcount(conn: DbDep, _: RateLimitDep) -> list[dict[str, Any]]:
        """Retrieve employee headcount distribution per department."""
        return TechCorpAnalytics(conn).headcount_by_department()

    @app.get(
        "/projects/durations",
        response_model=list[ProjectDurationItem],
        tags=["Analytics"],
    )
    def project_durations(conn: DbDep, _: RateLimitDep) -> list[dict[str, Any]]:
        """Retrieve project turnaround duration metrics in days."""
        return TechCorpAnalytics(conn).project_duration_metrics()

    @app.get(
        "/projects/high-value",
        response_model=list[HighValueProjectItem],
        tags=["Analytics"],
    )
    def high_value_projects(
        conn: DbDep,
        _: RateLimitDep,
        min_budget: float = Query(default=25000.0, ge=0.0),
        inclusive: bool = Query(default=False),
    ) -> list[dict[str, Any]]:
        """Identify strategic projects exceeding the specified budget threshold."""
        return TechCorpAnalytics(conn).high_value_projects(
            min_budget=min_budget,
            inclusive=inclusive,
        )

    @app.get("/governance", response_model=list[GovernanceItem], tags=["Governance"])
    def executive_governance(
        request: Request,
        conn: DbDep,
        _: RateLimitDep,
        senior_cutoff: str | None = Query(default=None),
    ) -> list[dict[str, Any]]:
        """Map departments and projects to senior staff leads prior to cutoff date."""
        cfg: Settings = request.app.state.settings
        cutoff = senior_cutoff or cfg.senior_cutoff_date
        return TechCorpAnalytics(conn).executive_governance_report(senior_cutoff=cutoff)

    @app.get("/employees", response_model=list[EmployeeItem], tags=["Directory"])
    def list_employees(
        conn: DbDep,
        _: RateLimitDep,
        department: str | None = Query(default=None),
    ) -> list[dict[str, Any]]:
        """List employees joined with department assignments."""
        return TechCorpRepository(conn).list_employees_with_department(department_name=department)

    @app.patch(
        "/projects/{project_id}/budget",
        response_model=BudgetUpdateResponse,
        tags=["Lifecycle"],
    )
    def update_project_budget(
        project_id: int,
        payload: BudgetUpdateRequest,
        request: Request,
        conn: DbDep,
        _: RateLimitDep,
    ) -> dict[str, Any]:
        """Update a project's budget and invalidate cached analytics."""
        updated = TechCorpRepository(conn).update_project_budget(project_id, payload.budget)
        request.app.state.cache.clear()
        return {
            "project_id": int(updated["project_id"]),
            "project_name": str(updated["project_name"]),
            "previous_budget": float(updated["previous_budget"]),
            "budget": float(updated["budget"]),
            "department_name": str(updated["department_name"]),
        }

    @app.delete(
        "/employees/{employee_id}",
        response_model=OffboardResponse,
        tags=["Lifecycle"],
    )
    def offboard_employee(
        employee_id: int,
        request: Request,
        conn: DbDep,
        _: RateLimitDep,
    ) -> dict[str, Any]:
        """Remove an offboarded employee record and clear analytics cache."""
        TechCorpRepository(conn).offboard_employee(employee_id, raise_if_missing=True)
        request.app.state.cache.clear()
        return {"employee_id": employee_id, "offboarded": True}


def create_app(
    settings: Settings | None = None,
    *,
    read_only: bool = False,
) -> FastAPI:
    """Create and configure a TechCorp Analytics FastAPI application instance.

    Args:
        settings: Optional custom ``Settings`` object; defaults to environment config.
        read_only: Open SQLite connections in read-only URI mode when True.

    Returns:
        Configured ``FastAPI`` application.
    """
    resolved_settings = settings or get_settings()
    configure_logging(resolved_settings.log_level)

    app = FastAPI(
        title="TechCorp SQL Data Analytics API",
        version="1.0.0",
        description="Modular SQLite Business Intelligence and governance API for TechCorp.",
    )
    app.state.settings = resolved_settings
    app.state.read_only = read_only
    app.state.cache = AnalyticsCache(ttl_seconds=resolved_settings.cache_ttl_seconds)
    app.state.rate_limiter = InMemoryRateLimiter(
        max_requests=resolved_settings.rate_limit_requests,
        window_seconds=resolved_settings.rate_limit_window_seconds,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(resolved_settings.cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
    )

    _register_exception_handlers(app)
    _register_routes(app)
    return app


app = create_app()
