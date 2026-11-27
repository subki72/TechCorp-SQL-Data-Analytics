# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-11-27

### Added
- Modular Python package under `src/techcorp_analytics/` (`config.py`, `database.py`, `repository.py`, `analytics.py`, `api.py`).
- Idempotent SQLite DDL migration script `migrations/001_techcorp_schema.sql` with foreign key constraints, `CHECK (budget >= 0)`, and query indexes.
- Dual-mode CLI entrypoint `main.py` supporting `--health`, `--demo`, and `--serve`.
- FastAPI service with `/health`, `/analyze`, department/project/governance endpoints, Pydantic v2 validation, CORS middleware, TTL caching, sliding-window rate limiting, and centralized JSON error handlers.
- Comprehensive offline test suite across `tests/` (`test_database.py`, `test_repository.py`, `test_analytics.py`, `test_api.py`, `test_cli_and_notebook.py`).
- Production tooling: `.gitignore`, `.env.example`, `pyproject.toml`, `requirements.txt`, `Dockerfile`, `docker-compose.yml`, `Makefile`, CI/release workflows, Dependabot, pre-commit config, ADR-001, `CONTRIBUTING.md`, `SECURITY.md`, and `docs/runbook.md`.

### Fixed
- Enabled `PRAGMA foreign_keys = ON` in both `Portfolio_V3_TechCorp_Engineering.ipynb` (Cell 2) and `src/techcorp_analytics/database.py`.
- Removed orphan `DROP TABLE IF EXISTS Assignments` from notebook Cell 2, redirected default notebook execution to `techcorp_demo.sqlite` to protect `techcorp_db.sqlite`, fixed the misleading `"DOCX Source"` log message in Cell 4, resolved the Seaborn v0.14 `FutureWarning` in Cell 8 (`hue='department_name', legend=False`), and added a clean `conn.close()` cell.
- Replaced placeholder repository URL (`yourusername`) with `subki72` in `README.md`.

## [0.1.0] - 2025-12-20

### Added
- Initial exploratory SQLite portfolio notebook (`Portfolio_V3_TechCorp_Engineering.ipynb`), sample snapshot (`techcorp_db.sqlite`), MIT `LICENSE`, and baseline `README.md`.
