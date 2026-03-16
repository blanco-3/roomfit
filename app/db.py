from __future__ import annotations

import hashlib
import json
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from app.db_backend import PostgresBackendNotImplemented, SQLiteBackend, parse_database_url

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = BASE_DIR / "data" / "roomstyler.db"
CATALOG_PATH = BASE_DIR / "data" / "furniture_catalog.json"
UPLOAD_DIR = BASE_DIR / "data" / "uploads"

DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DEFAULT_DB_PATH}")

_cfg = parse_database_url(DATABASE_URL)
if _cfg.engine == "sqlite":
    _db = SQLiteBackend(Path(_cfg.database))
else:
    _db = PostgresBackendNotImplemented(_cfg.database)


def conn():
    return _db.connect()


def hash_password(password: str, salt: str) -> str:
    return hashlib.sha256(f"{salt}:{password}".encode("utf-8")).hexdigest()


def init_db() -> None:
    if _cfg.engine != "sqlite":
        return

    db_path = Path(_cfg.database)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    with conn() as c:
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
              user_id TEXT PRIMARY KEY,
              email TEXT UNIQUE NOT NULL,
              password_hash TEXT NOT NULL,
              password_salt TEXT NOT NULL,
              display_name TEXT NOT NULL,
              created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS auth_tokens (
              token TEXT PRIMARY KEY,
              user_id TEXT NOT NULL,
              created_at TEXT DEFAULT CURRENT_TIMESTAMP,
              FOREIGN KEY(user_id) REFERENCES users(user_id)
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS room_profiles (
              room_id TEXT PRIMARY KEY,
              user_id TEXT NOT NULL,
              width_cm INTEGER NOT NULL,
              length_cm INTEGER NOT NULL,
              height_cm INTEGER NOT NULL,
              mood TEXT NOT NULL,
              purpose TEXT NOT NULL,
              budget_krw INTEGER NOT NULL,
              area_m2 REAL NOT NULL,
              estimate_source TEXT NOT NULL DEFAULT 'manual',
              estimate_confidence REAL,
              estimation_notes TEXT,
              created_at TEXT DEFAULT CURRENT_TIMESTAMP,
              updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
              FOREIGN KEY(user_id) REFERENCES users(user_id)
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS room_photos (
              photo_id TEXT PRIMARY KEY,
              room_id TEXT NOT NULL,
              file_path TEXT NOT NULL,
              original_name TEXT NOT NULL,
              created_at TEXT DEFAULT CURRENT_TIMESTAMP,
              FOREIGN KEY(room_id) REFERENCES room_profiles(room_id)
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS recommendation_runs (
              run_id TEXT PRIMARY KEY,
              room_id TEXT NOT NULL,
              total_price_krw INTEGER NOT NULL,
              fit_score REAL NOT NULL,
              style_score REAL NOT NULL,
              selected_count INTEGER NOT NULL,
              payload_json TEXT NOT NULL,
              idempotency_key TEXT,
              created_at TEXT DEFAULT CURRENT_TIMESTAMP,
              FOREIGN KEY(room_id) REFERENCES room_profiles(room_id)
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS ops_logs (
              log_id TEXT PRIMARY KEY,
              event_type TEXT NOT NULL,
              level TEXT NOT NULL,
              message TEXT NOT NULL,
              context_json TEXT NOT NULL,
              created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS cv_jobs (
              job_id TEXT PRIMARY KEY,
              room_id TEXT NOT NULL,
              user_id TEXT NOT NULL,
              status TEXT NOT NULL,
              result_json TEXT,
              error_text TEXT,
              idempotency_key TEXT,
              retry_count INTEGER NOT NULL DEFAULT 0,
              started_at TEXT,
              timeout_seconds INTEGER,
              created_at TEXT DEFAULT CURRENT_TIMESTAMP,
              updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
              FOREIGN KEY(room_id) REFERENCES room_profiles(room_id),
              FOREIGN KEY(user_id) REFERENCES users(user_id)
            )
            """
        )

        # lightweight migration for existing sqlite files
        columns = {row['name'] for row in c.execute("PRAGMA table_info(room_profiles)").fetchall()}
        if 'estimate_source' not in columns:
            c.execute("ALTER TABLE room_profiles ADD COLUMN estimate_source TEXT NOT NULL DEFAULT 'manual'")
        if 'estimate_confidence' not in columns:
            c.execute("ALTER TABLE room_profiles ADD COLUMN estimate_confidence REAL")
        if 'estimation_notes' not in columns:
            c.execute("ALTER TABLE room_profiles ADD COLUMN estimation_notes TEXT")
        if 'updated_at' not in columns:
            c.execute("ALTER TABLE room_profiles ADD COLUMN updated_at TEXT")
            c.execute("UPDATE room_profiles SET updated_at = created_at WHERE updated_at IS NULL")

        rec_columns = {row['name'] for row in c.execute("PRAGMA table_info(recommendation_runs)").fetchall()}
        if 'idempotency_key' not in rec_columns:
            c.execute("ALTER TABLE recommendation_runs ADD COLUMN idempotency_key TEXT")

        cv_columns = {row['name'] for row in c.execute("PRAGMA table_info(cv_jobs)").fetchall()}
        if 'idempotency_key' not in cv_columns:
            c.execute("ALTER TABLE cv_jobs ADD COLUMN idempotency_key TEXT")
        if 'retry_count' not in cv_columns:
            c.execute("ALTER TABLE cv_jobs ADD COLUMN retry_count INTEGER NOT NULL DEFAULT 0")
        if 'started_at' not in cv_columns:
            c.execute("ALTER TABLE cv_jobs ADD COLUMN started_at TEXT")
        if 'timeout_seconds' not in cv_columns:
            c.execute("ALTER TABLE cv_jobs ADD COLUMN timeout_seconds INTEGER")


def log_event(event_type: str, message: str, *, level: str = "info", context: Optional[dict] = None) -> str:
    log_id = str(uuid.uuid4())
    with conn() as c:
        c.execute(
            "INSERT INTO ops_logs (log_id, event_type, level, message, context_json) VALUES (?, ?, ?, ?, ?)",
            (
                log_id,
                event_type,
                level,
                message,
                json.dumps(context or {}, ensure_ascii=False),
            ),
        )
    return log_id


def list_ops_logs(limit: int = 50) -> list[dict]:
    with conn() as c:
        rows = c.execute(
            "SELECT log_id, event_type, level, message, context_json, created_at FROM ops_logs ORDER BY created_at DESC LIMIT ?",
            (max(1, min(limit, 200)),),
        ).fetchall()
    out = []
    for row in rows:
        item = dict(row)
        try:
            item["context"] = json.loads(item.pop("context_json"))
        except Exception:
            item["context"] = {"raw": item.pop("context_json")}
        out.append(item)
    return out


def create_user(email: str, password: str, display_name: str) -> dict:
    user_id = str(uuid.uuid4())
    salt = secrets.token_hex(16)
    password_hash = hash_password(password, salt)
    with conn() as c:
        c.execute(
            "INSERT INTO users (user_id, email, password_hash, password_salt, display_name) VALUES (?, ?, ?, ?, ?)",
            (user_id, email.lower(), password_hash, salt, display_name),
        )
    return {"user_id": user_id, "email": email.lower(), "display_name": display_name}


def authenticate_user(email: str, password: str) -> Optional[dict]:
    with conn() as c:
        row = c.execute("SELECT * FROM users WHERE email = ?", (email.lower(),)).fetchone()
    if not row:
        return None
    if hash_password(password, row["password_salt"]) != row["password_hash"]:
        return None
    return {"user_id": row["user_id"], "email": row["email"], "display_name": row["display_name"]}


def create_token(user_id: str) -> str:
    token = secrets.token_urlsafe(32)
    with conn() as c:
        c.execute("INSERT INTO auth_tokens (token, user_id) VALUES (?, ?)", (token, user_id))
    return token


def get_user_by_token(token: str) -> Optional[dict]:
    with conn() as c:
        row = c.execute(
            """
            SELECT u.user_id, u.email, u.display_name
            FROM auth_tokens t
            JOIN users u ON u.user_id = t.user_id
            WHERE t.token = ?
            """,
            (token,),
        ).fetchone()
    return dict(row) if row else None


def save_room(user_id: str, payload: dict) -> dict:
    room_id = payload.get("room_id") or str(uuid.uuid4())
    area_m2 = round((payload["width_cm"] * payload["length_cm"]) / 10000, 2)
    estimate_source = payload.get("estimate_source", "manual")
    estimate_confidence = payload.get("estimate_confidence")
    estimation_notes = payload.get("estimation_notes")

    with conn() as c:
        exists = c.execute("SELECT room_id FROM room_profiles WHERE room_id = ?", (room_id,)).fetchone()
        if exists:
            c.execute(
                """
                UPDATE room_profiles
                SET width_cm = ?, length_cm = ?, height_cm = ?, mood = ?, purpose = ?, budget_krw = ?,
                    area_m2 = ?, estimate_source = ?, estimate_confidence = ?, estimation_notes = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE room_id = ? AND user_id = ?
                """,
                (
                    payload["width_cm"],
                    payload["length_cm"],
                    payload["height_cm"],
                    payload["mood"],
                    payload["purpose"],
                    payload["budget_krw"],
                    area_m2,
                    estimate_source,
                    estimate_confidence,
                    estimation_notes,
                    room_id,
                    user_id,
                ),
            )
        else:
            c.execute(
                """
                INSERT INTO room_profiles
                (room_id, user_id, width_cm, length_cm, height_cm, mood, purpose, budget_krw, area_m2,
                 estimate_source, estimate_confidence, estimation_notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    room_id,
                    user_id,
                    payload["width_cm"],
                    payload["length_cm"],
                    payload["height_cm"],
                    payload["mood"],
                    payload["purpose"],
                    payload["budget_krw"],
                    area_m2,
                    estimate_source,
                    estimate_confidence,
                    estimation_notes,
                ),
            )
    return {
        "room_id": room_id,
        "area_m2": area_m2,
        "estimate_source": estimate_source,
        "estimate_confidence": estimate_confidence,
    }


def get_room(room_id: str) -> Optional[dict]:
    with conn() as c:
        row = c.execute("SELECT * FROM room_profiles WHERE room_id = ?", (room_id,)).fetchone()
    return dict(row) if row else None


def count_room_photos(room_id: str) -> int:
    with conn() as c:
        row = c.execute("SELECT COUNT(*) as cnt FROM room_photos WHERE room_id = ?", (room_id,)).fetchone()
    return int(row["cnt"] if row else 0)


def create_cv_job(
    room_id: str,
    user_id: str,
    *,
    idempotency_key: Optional[str] = None,
    timeout_seconds: int = 90,
) -> str:
    job_id = str(uuid.uuid4())
    with conn() as c:
        c.execute(
            "INSERT INTO cv_jobs (job_id, room_id, user_id, status, idempotency_key, timeout_seconds) VALUES (?, ?, ?, ?, ?, ?)",
            (job_id, room_id, user_id, "queued", idempotency_key, timeout_seconds),
        )
    return job_id


def update_cv_job(job_id: str, status: str, *, result: Optional[dict] = None, error_text: Optional[str] = None) -> None:
    started_at = datetime.now(timezone.utc).isoformat() if status == "running" else None
    with conn() as c:
        c.execute(
            """
            UPDATE cv_jobs
            SET status = ?, result_json = ?, error_text = ?,
                started_at = COALESCE(?, started_at),
                retry_count = CASE WHEN ? = 'running' THEN retry_count + 1 ELSE retry_count END,
                updated_at = CURRENT_TIMESTAMP
            WHERE job_id = ?
            """,
            (status, json.dumps(result, ensure_ascii=False) if result else None, error_text, started_at, status, job_id),
        )


def get_cv_job(job_id: str) -> Optional[dict]:
    with conn() as c:
        row = c.execute(
            "SELECT job_id, room_id, user_id, status, result_json, error_text, idempotency_key, retry_count, started_at, timeout_seconds, created_at, updated_at FROM cv_jobs WHERE job_id = ?",
            (job_id,),
        ).fetchone()
    if not row:
        return None
    item = dict(row)
    if item.get("result_json"):
        try:
            item["result"] = json.loads(item["result_json"])
        except Exception:
            item["result"] = None
    else:
        item["result"] = None
    item.pop("result_json", None)
    return item


def find_reusable_cv_job(room_id: str, user_id: str, idempotency_key: Optional[str]) -> Optional[dict]:
    if not idempotency_key:
        return None
    with conn() as c:
        row = c.execute(
            """
            SELECT job_id FROM cv_jobs
            WHERE room_id = ? AND user_id = ? AND idempotency_key = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (room_id, user_id, idempotency_key),
        ).fetchone()
    if not row:
        return None
    return get_cv_job(row["job_id"])


def mark_stale_cv_jobs_as_timed_out(timeout_seconds: int = 90) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=max(1, timeout_seconds))
    with conn() as c:
        rows = c.execute(
            "SELECT job_id, started_at FROM cv_jobs WHERE status = 'running'"
        ).fetchall()
        stale_ids = []
        for row in rows:
            started_at = row["started_at"]
            if not started_at:
                continue
            try:
                started_dt = datetime.fromisoformat(started_at)
            except ValueError:
                continue
            if started_dt <= cutoff:
                stale_ids.append(row["job_id"])

        for job_id in stale_ids:
            c.execute(
                "UPDATE cv_jobs SET status = 'failed', error_text = 'timeout', updated_at = CURRENT_TIMESTAMP WHERE job_id = ?",
                (job_id,),
            )

    return len(stale_ids)


def save_room_photo(room_id: str, original_name: str, file_bytes: bytes) -> dict:
    photo_id = str(uuid.uuid4())
    room_path = UPLOAD_DIR / room_id
    room_path.mkdir(parents=True, exist_ok=True)

    ext = Path(original_name).suffix.lower() or ".jpg"
    filename = f"{photo_id}{ext}"
    file_path = room_path / filename
    file_path.write_bytes(file_bytes)

    with conn() as c:
        c.execute(
            "INSERT INTO room_photos (photo_id, room_id, file_path, original_name) VALUES (?, ?, ?, ?)",
            (photo_id, room_id, str(file_path), original_name),
        )

    return {"photo_id": photo_id, "file_path": str(file_path), "original_name": original_name}


def save_recommendation(room_id: str, result: dict, *, idempotency_key: Optional[str] = None) -> str:
    run_id = str(uuid.uuid4())
    summary = result["summary"]
    with conn() as c:
        c.execute(
            """
            INSERT INTO recommendation_runs
            (run_id, room_id, total_price_krw, fit_score, style_score, selected_count, payload_json, idempotency_key)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                room_id,
                summary["total_price_krw"],
                summary["fit_score"],
                summary["style_score"],
                summary["selected_count"],
                json.dumps(result, ensure_ascii=False),
                idempotency_key,
            ),
        )
    return run_id


def find_recommendation_by_key(room_id: str, idempotency_key: Optional[str]) -> Optional[dict]:
    if not idempotency_key:
        return None
    with conn() as c:
        row = c.execute(
            """
            SELECT run_id, payload_json
            FROM recommendation_runs
            WHERE room_id = ? AND idempotency_key = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (room_id, idempotency_key),
        ).fetchone()
    if not row:
        return None
    payload = json.loads(row["payload_json"])
    payload["run_id"] = row["run_id"]
    return payload


def list_recommendation_runs(user_id: str, limit: int = 20) -> list[dict]:
    with conn() as c:
        rows = c.execute(
            """
            SELECT rr.run_id, rr.room_id, rr.total_price_krw, rr.fit_score, rr.style_score, rr.selected_count, rr.created_at
            FROM recommendation_runs rr
            JOIN room_profiles rp ON rr.room_id = rp.room_id
            WHERE rp.user_id = ?
            ORDER BY rr.created_at DESC
            LIMIT ?
            """,
            (user_id, max(1, min(limit, 100))),
        ).fetchall()
    return [dict(row) for row in rows]


def load_catalog() -> list[dict]:
    with open(CATALOG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)
