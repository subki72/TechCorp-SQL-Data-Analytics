## Summary

Describe the motivation, scope, and database/API changes included in this pull request.

## Type of Change

- [ ] Bug fix (non-breaking change fixing an issue)
- [ ] New feature (non-breaking change adding functionality)
- [ ] Schema migration (`migrations/*.sql`)
- [ ] Documentation or governance update

## Verification Checklist

- [ ] `python -m ruff check src tests main.py` passes with 0 errors
- [ ] `python -m ruff format --check src tests main.py` passes
- [ ] `python -m flake8 --max-line-length=120 src tests main.py` passes
- [ ] `python -m pytest tests/ -v --cov=src --cov-fail-under=75` passes (100% offline)
- [ ] `python main.py --health` and `python main.py --demo` succeed without mutating `techcorp_db.sqlite`
- [ ] No `.env`, credentials, or temporary SQLite journal files are staged
