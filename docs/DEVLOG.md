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

## 2026-03-16 04:19 KST
- Added practical product improvements for launch UX:
  - New API endpoint: `GET /v1/recommendations/history` (authenticated user history).
  - Main UI upgraded with: height input, loading/busy button state, logout, robust JSON error handling, recommendation history panel, history refresh action.
- Added architecture + cost research documentation track:
  - `docs/ROADMAP.md` (phased architecture: now → MVP AI → growth → scale)
  - `docs/COST_MODEL_RESEARCH.md` (cost bands, stack choices, tradeoffs, fallback options)
- Extended tests:
  - Added history endpoint test (`test_recommendation_history_endpoint`).
- Tests:
  - `PYTHONPATH=. .venv/bin/pytest -q`
  - Result: **4 passed**.
- Next:
  - Add CV worker scaffolding + async job model with mocked room measurement estimation.
  - Migrate startup hook to lifespan (remove deprecation warnings).
