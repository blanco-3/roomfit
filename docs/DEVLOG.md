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

## 2026-03-16 04:21 KST
- Implemented CV-worker scaffolding (cost-free mock path):
  - Added `app/cv_worker.py` with mocked measurement estimation heuristic.
  - Added async-job style DB model in `cv_jobs` table.
  - Added DB helpers: create/update/get CV jobs + room photo count helper.
  - Added APIs:
    - `POST /v1/cv/jobs?room_id=...` (queue + run mock estimation)
    - `GET /v1/cv/jobs/{job_id}` (job 상태/결과 조회)
- Added test coverage for end-to-end mocked CV job flow including photo upload.
- Tests:
  - `PYTHONPATH=. .venv/bin/pytest -q`
  - Result: **5 passed**.
- Next:
  - Remove FastAPI startup deprecation warning using lifespan.
  - Add migration-ready SQL docs/scripts for Postgres transition.

## 2026-03-16 04:22 KST
- Backend quality hardening:
  - Switched FastAPI startup handling to `lifespan` (deprecation warning 제거).
  - Test bootstrap now explicitly initializes DB for deterministic runs.
- Postgres migration path artifacts added:
  - `docs/POSTGRES_MIGRATION.md` (cutover strategy + checklist)
  - `scripts/export_sqlite_to_json.py` (SQLite 데이터 export)
- README updated with migration/export references.
- Tests:
  - `PYTHONPATH=. .venv/bin/pytest -q`
  - Result: **5 passed** (warnings resolved).
- Next:
  - Add richer UX affordances (form validation hints, endpoint-driven status chips).
  - Prepare worker queue abstraction (in-process now, Redis-ready interface next).

## 2026-03-16 09:44 KST
- Priority 1 (AI-assisted room sizing) implemented:
  - Added mocked local CV inference utility `infer_room_dimensions_from_photos()` in `app/cv_worker.py`.
  - Added new API: `POST /v1/room/auto-estimate` (multipart; photos + `reference_object`) to infer rough dimensions and confidence.
  - Enhanced `room_profiles` model with estimation metadata (`estimate_source`, `estimate_confidence`, `estimation_notes`, `updated_at`) + SQLite in-place migration logic.
  - Updated `/v1/room/estimate` to support editable fallback/update using optional `room_id` while keeping existing manual payload compatibility.
  - Recommendation response now includes `room_estimation` metadata to show whether results came from manual vs AI-reviewed dimensions.
- Priority 2 (major UI/UX redesign) implemented:
  - Rebuilt `app/static/index.html` into 5-step mobile-first wizard:
    1) account/login
    2) room basics (+ optional manual dimensions)
    3) photo upload and reference object selection
    4) AI estimation review/edit
    5) recommendation results + rationale/history
  - Rewrote `app/static/styles.css` with card hierarchy, spacing, inline validation messages, and sticky primary CTA.
  - Preserved PWA behavior (`manifest` + service worker registration retained).
- Tests:
  - Added `test_auto_estimate_from_photos_and_recommendation_flow` for new critical path.
