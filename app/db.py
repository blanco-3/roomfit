from __future__ import annotations

import hashlib
import json
import os
import secrets
import uuid
from datetime import datetime, timezone
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
              created_at TEXT DEFAULT CURRENT_TIMESTAMP,
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
    room_id = str(uuid.uuid4())
    area_m2 = round((payload["width_cm"] * payload["length_cm"]) / 10000, 2)

    with conn() as c:
        c.execute(
            """
            INSERT INTO room_profiles (room_id, user_id, width_cm, length_cm, height_cm, mood, purpose, budget_krw, area_m2)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            ),
        )
    return {"room_id": room_id, "area_m2": area_m2}


def get_room(room_id: str) -> Optional[dict]:
    with conn() as c:
        row = c.execute("SELECT * FROM room_profiles WHERE room_id = ?", (room_id,)).fetchone()
    return dict(row) if row else None


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


def save_recommendation(room_id: str, result: dict) -> str:
    run_id = str(uuid.uuid4())
    summary = result["summary"]
    with conn() as c:
        c.execute(
            """
            INSERT INTO recommendation_runs
            (run_id, room_id, total_price_krw, fit_score, style_score, selected_count, payload_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                room_id,
                summary["total_price_krw"],
                summary["fit_score"],
                summary["style_score"],
                summary["selected_count"],
                json.dumps(result, ensure_ascii=False),
            ),
        )
    return run_id


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
