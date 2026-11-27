# TechCorp Data Engineering & SQL Analytics Platform

[![CI Pipeline](https://github.com/subki72/TechCorp-SQL-Data-Analytics/actions/workflows/ci.yml/badge.svg)](https://github.com/subki72/TechCorp-SQL-Data-Analytics/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.136-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![SQLite](https://img.shields.io/badge/SQLite-PRAGMA%20FK%20ON-003B57?logo=sqlite&logoColor=white)](https://www.sqlite.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## Project Overview

This repository implements a production-grade SQLite data engineering, relational governance, and Business Intelligence (BI) analytics platform for **TechCorp**. It preserves the interactive exploratory notebook (`Portfolio_V3_TechCorp_Engineering.ipynb`) while modularizing schema migrations, transaction-safe CRUD operations, analytical reporting, CLI execution, and a FastAPI service into a clean Python package under `src/techcorp_analytics/`.

## Architecture & Repository Layout

```text
TechCorp-SQL-Data-Analytics/
├── .github/
│   ├── workflows/
│   │   ├── ci.yml                 # Ruff, Flake8, Mypy, Pytest >=75% cov, Semgrep, Docker + Trivy
│   │   └── release.yml            # Tagged v*.*.* wheel/sdist, container, and GitHub Release
│   ├── dependabot.yml             # Weekly pip/docker/actions updates (semver-major ignored)
│   └── PULL_REQUEST_TEMPLATE.md
├── docs/
│   ├── adr/
│   │   └── 001-relational-sqlite-governance.md
│   └── runbook.md                 # Incident triage, backup/restore, and health diagnostics
├── migrations/
│   └── 001_techcorp_schema.sql    # Idempotent DDL with FKs, budget CHECK, and indexes
├── src/
│   └── techcorp_analytics/
│       ├── __init__.py
│       ├── config.py              # Externalized env settings & structured logging
│       ├── database.py            # Context-managed SQLite connections (PRAGMA foreign_keys = ON)
│       ├── repository.py          # Parameterized transactional CRUD operations
│       ├── analytics.py           # BI queries, executive governance report & TTL cache
│       └── api.py                 # FastAPI service (/health, /analyze, CORS, rate limit)
├── tests/                         # Offline unit & API integration tests (97%+ coverage)
├── main.py                        # Dual-mode CLI (--health, --demo, --serve)
├── Portfolio_V3_TechCorp_Engineering.ipynb
├── techcorp_db.sqlite             # Read-only reference snapshot from original analysis
├── Dockerfile                     # Multi-stage Python 3.11-slim non-root container
├── docker-compose.yml
├── Makefile
├── pyproject.toml
└── requirements.txt
```

## Relational Schema & Referential Integrity

Three normalized tables live in `migrations/001_techcorp_schema.sql`:

| Table | Primary Key | Constraints & Foreign Keys | Indexes |
|---|---|---|---|
| `Departments` | `department_id` | `department_name TEXT NOT NULL UNIQUE` | Primary key |
| `Employees` | `employee_id` | `email UNIQUE`, `FOREIGN KEY (department_id) REFERENCES Departments(department_id) ON DELETE RESTRICT ON UPDATE CASCADE` | `idx_employees_department_id`, `idx_employees_hire_date` |
| `Projects` | `project_id` | `CHECK (budget >= 0)`, `FOREIGN KEY (department_id) REFERENCES Departments(department_id) ON DELETE RESTRICT ON UPDATE CASCADE` | `idx_projects_department_id`, `idx_projects_budget` |

Every SQLite connection opened through `src/techcorp_analytics/database.py` enforces `PRAGMA foreign_keys = ON;` and transaction rollback on error.

## Key Engineering Improvements

- **Strict SQLite Integrity**: Enabled `PRAGMA foreign_keys = ON` both in `database.py` and in Cell 2 of `Portfolio_V3_TechCorp_Engineering.ipynb`, preventing orphan employees or projects.
- **Notebook Reliability Fixes**: Removed orphan `DROP TABLE IF EXISTS Assignments`, isolated notebook execution to `TECHCORP_NOTEBOOK_DB` (`techcorp_demo.sqlite`) so `techcorp_db.sqlite` is never mutated unintentionally, fixed the misleading `"DOCX Source"` log message, fixed the Seaborn v0.14 `FutureWarning` (`hue='department_name', legend=False`), and added a closing `conn.close()` cell.
- **Zero-SQL API Layer**: All parameterized SQL statements remain encapsulated inside `repository.py`, `analytics.py`, and `database.py`.
- **Operational Resilience**: Added TTL caching (`AnalyticsCache`), sliding-window rate limiting (`InMemoryRateLimiter`), `CORSMiddleware`, centralized JSON exception handlers, and read-only health checks.

## Quickstart

### 1. Clone and Configure

```bash
git clone https://github.com/subki72/TechCorp-SQL-Data-Analytics.git
cd TechCorp-SQL-Data-Analytics
cp .env.example .env
make install-dev
```

### 2. Run Health Check, Demo, Lint, and Tests

```bash
make health       # Verifies techcorp_db.sqlite schema & PRAGMA foreign_keys read-only
make demo         # Runs full CRUD + BI analytics pipeline in isolated :memory: DB
make lint         # Runs Ruff check, Ruff format check, and Flake8
make test         # Runs Pytest offline suite with coverage gate (>= 75%)
```

### 3. Run the FastAPI Service or Docker Container

```bash
# Local development server
make run

# Or build and start with Docker Compose
docker compose up --build
```

## REST API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Readiness probe verifying schema tables, `PRAGMA foreign_keys`, and row counts |
| `GET` | `/analyze` | Consolidated BI summary (TTL-cached) across budgets, headcount, durations, and governance |
| `GET` | `/departments/budgets` | Project count, total budget, and average budget per department |
| `GET` | `/departments/headcount` | Workforce distribution per department |
| `GET` | `/projects/durations` | Project duration metrics (`julianday(end_date) - julianday(start_date)`) |
| `GET` | `/projects/high-value` | Strategic projects filtered by `min_budget` (default `25000`) |
| `GET` | `/governance` | Executive report mapping projects to senior managers (`hire_date < senior_cutoff`) |
| `GET` | `/employees` | Employee directory joined with department names (optional `?department=IT`) |
| `PATCH` | `/projects/{project_id}/budget` | Transactional budget adjustment with cache invalidation |
| `DELETE` | `/employees/{employee_id}` | Employee offboarding with `404` handling and cache invalidation |

## Business Intelligence Highlights

- **Budget Concentration**: The **IT Department** leads project investment ($130,000 across *Website Redesign* and *App Development*, rising to $140,000 after budget adjustment).
- **High-Value Projects (`> $25,000`)**: *App Development* ($80,000), *Website Redesign* ($50,000 initial / $60,000 revised), and *Sales Strategy* ($30,000).
- **Timeline Turnaround**: Strategic initiatives (*Sales Strategy*, *App Development*) span 213 days compared to 60 days for *Financial Audit*.

## License

Licensed under the [MIT License](LICENSE).
