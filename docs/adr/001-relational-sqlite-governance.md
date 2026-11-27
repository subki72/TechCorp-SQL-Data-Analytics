# ADR-001: Relational SQLite Governance and Dual-Mode Service Architecture

- **Status**: Accepted
- **Date**: 2026-11-27
- **Context**: The initial TechCorp repository consisted of a standalone Jupyter notebook (`Portfolio_V3_TechCorp_Engineering.ipynb`) and a mutated `techcorp_db.sqlite` snapshot. SQLite does not enable foreign key enforcement by default unless `PRAGMA foreign_keys = ON` is executed per connection, and exploratory notebooks lacked automated tests, layer separation, input validation, and reproducible runtime packaging.

## Decision

1. **Per-Connection Foreign Key Enforcement**: Every SQLite connection created by `src/techcorp_analytics/database.py` executes `PRAGMA foreign_keys = ON`, validates pragma activation, sets explicit lock timeouts, and guarantees commit/rollback/close via a context manager.
2. **Versioned Idempotent Migrations**: Schema definitions live in `migrations/001_techcorp_schema.sql` with `ON DELETE RESTRICT`, `ON UPDATE CASCADE`, `CHECK (budget >= 0)`, and targeted indexes for frequent BI joins.
3. **Strict Layer Separation**:
   - `repository.py`: Transactional parameterized CRUD operations and domain validation.
   - `analytics.py`: Read-heavy BI aggregations, governance reporting, and TTL caching (`AnalyticsCache`).
   - `api.py`: FastAPI HTTP transport, Pydantic v2 DTOs, `CORSMiddleware`, sliding-window rate limiting, and centralized JSON error handlers — containing zero SQL statements.
4. **Dual-Mode Non-Breaking Entrypoints**: Both the patched notebook (isolated to `TECHCORP_NOTEBOOK_DB`) and `main.py` (`--health`, `--demo`, `--serve`) operate cleanly without altering the committed `techcorp_db.sqlite` snapshot during tests or CI runs.

## Consequences

- **Positive**: High testability (97%+ unit and integration coverage using isolated `:memory:` and `tmp_path` databases), strict FK integrity, and zero risk of accidental snapshot corruption in CI.
- **Trade-off**: SQLite remains single-writer; scaling to concurrent multi-node writes in the future will require swapping the connection factory in `database.py` for PostgreSQL while preserving repository/analytics interfaces.
