from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "roomstyler.db"
CATALOG_PATH = BASE_DIR / "data" / "furniture_catalog.json"


def conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with conn() as c:
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS room_profiles (
              room_id TEXT PRIMARY KEY,
              width_cm INTEGER NOT NULL,
              length_cm INTEGER NOT NULL,
              height_cm INTEGER NOT NULL,
              mood TEXT NOT NULL,
              purpose TEXT NOT NULL,
              budget_krw INTEGER NOT NULL,
              area_m2 REAL NOT NULL,
              created_at TEXT DEFAULT CURRENT_TIMESTAMP
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


def save_room(payload: dict) -> dict:
    room_id = str(uuid.uuid4())
    area_m2 = round((payload["width_cm"] * payload["length_cm"]) / 10000, 2)

    with conn() as c:
        c.execute(
            """
            INSERT INTO room_profiles (room_id, width_cm, length_cm, height_cm, mood, purpose, budget_krw, area_m2)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                room_id,
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


def load_catalog() -> list[dict]:
    with open(CATALOG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)
