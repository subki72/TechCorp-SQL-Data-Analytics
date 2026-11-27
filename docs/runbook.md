# Operations Runbook — TechCorp SQL Data Analytics

## 1. Service Overview

- **Application**: `techcorp-analytics-api` (`src/techcorp_analytics/api.py`) and CLI (`main.py`)
- **Primary Store**: SQLite (`TECHCORP_DB_PATH`, default `techcorp_db.sqlite`)
- **Health Endpoint**: `GET /health` or `python main.py --health`

## 2. Health & Readiness Verification

### CLI Read-Only Probe
```bash
python main.py --health --db techcorp_db.sqlite
```
Expected fields in JSON output:
- `"status": "healthy"`
- `"database_ok": true`
- `"foreign_keys_enabled": true`
- `"tables": ["Departments", "Employees", "Projects"]`

### HTTP Probe
```bash
curl -fsS http://127.0.0.1:8000/health
```
Non-200 responses indicate missing tables (`400`), rate limiting (`429`), or an internal database connectivity issue (`500`).

## 3. Database Initialization & Migrations

- Migrations reside in `migrations/001_techcorp_schema.sql` and use `CREATE TABLE IF NOT EXISTS` and `CREATE INDEX IF NOT EXISTS`.
- Running `python main.py --serve --db /data/techcorp_runtime.sqlite` automatically applies migrations and seeds baseline TechCorp records if the target file does not yet exist.
- **Snapshot Protection**: Never point interactive notebooks or destructive tests at the committed `techcorp_db.sqlite` file. Use `:memory:`, a dedicated runtime path via `TECHCORP_DB_PATH`, or `TECHCORP_NOTEBOOK_DB`.

## 4. Incident Playbook

| Symptom | Likely Cause | Action |
|---|---|---|
| `400 Missing required database tables` | Pointed `TECHCORP_DB_PATH` at an empty/unmigrated SQLite file | Run `initialize_database(path, seed=True)` or start via `main.py --serve` |
| `422 foreign key reference does not exist` | Attempted employee/project write with invalid `department_id` | Verify `Departments` catalog via `GET /departments/budgets` before retry |
| `429 Too many requests` | Client exceeded `TECHCORP_RATE_LIMIT_REQUESTS` window | Wait for `TECHCORP_RATE_LIMIT_WINDOW_SECONDS` expiry or adjust env config |
| Stale `/analyze` totals after manual DB edit | External SQLite write bypassed API cache invalidation | Restart service or trigger a lifecycle update (`PATCH`/`DELETE`) or lower `TECHCORP_CACHE_TTL_SECONDS` |
| `database is locked` | Concurrent write contention on local disk | Increase `TECHCORP_REQUEST_TIMEOUT_SECONDS` and ensure no dangling notebook connections remain open |
