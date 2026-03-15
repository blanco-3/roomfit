# DEVLOG

## 2026-03-16 04:15 KST
- Restored runnable Python environment using `virtualenv` bootstrap (system `venv/ensurepip` unavailable).
- Implemented DB abstraction scaffold:
  - Added `app/db_backend.py` with URL parser + backend scaffolding.
  - Added `DATABASE_URL` support (default SQLite, Postgres-ready placeholder path).
- Added operations logging:
  - New `ops_logs` table in DB init.
  - `log_event()` + `list_ops_logs()` data access helpers.
  - Event logging wired into auth/login, room estimate, photo upload, recommendation flows.
  - New authenticated endpoint: `GET /v1/ops/logs?limit=`.
  - Added dashboard stub page: `/ops` (`app/static/ops.html`).
- Reliability fix:
  - Ensure DB schema initialization also runs at import-time for test/import usage.
- Tests:
  - `PYTHONPATH=. .venv/bin/pytest -q`
  - Result: **3 passed**.
- Next:
  - Upgrade UX quality in `app/static/index.html` (onboarding flow clarity, loading/error states, token/session handling).
  - Add API quality improvements useful for launch (room/profile retrieval + recent recommendation history endpoint).
