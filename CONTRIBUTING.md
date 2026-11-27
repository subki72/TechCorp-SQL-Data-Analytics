# Contributing Guide

Thank you for contributing to **TechCorp SQL Data Analytics**.

## Development Setup

1. Create and activate a Python 3.11+ virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```
2. Install runtime and development dependencies:
   ```bash
   make install-dev
   ```
3. Copy `.env.example` to `.env` if custom settings are needed. Never commit `.env`.

## Coding Standards

- Follow PEP 8 with Ruff (`line-length = 100`) and Flake8 (`max-line-length = 120`).
- Include explicit Python type hints (`mypy src` clean) and Google-style docstrings on public functions and classes.
- Keep all SQL queries strictly parameterized (`?`) inside `src/techcorp_analytics/repository.py`, `analytics.py`, or `database.py` — never inside `api.py` routes.
- Ensure every SQLite connection uses `get_connection(...)` so `PRAGMA foreign_keys = ON` and rollback/close guarantees are preserved.
- Use `logging.getLogger(__name__)` rather than bare `print()` inside `src/`.

## Verification Before Opening a Pull Request

Run all checks locally and ensure `techcorp_db.sqlite` remains unmodified:

```bash
make lint
make test
make health
make demo
```
