from __future__ import annotations

import json
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "roomstyler.db"
OUT_PATH = BASE_DIR / "data" / "sqlite_export.json"

TABLES = [
    "users",
    "auth_tokens",
    "room_profiles",
    "room_photos",
    "recommendation_runs",
    "ops_logs",
    "cv_jobs",
]


def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    dump = {}
    for table in TABLES:
        rows = conn.execute(f"SELECT * FROM {table}").fetchall()
        dump[table] = [dict(r) for r in rows]
    OUT_PATH.write_text(json.dumps(dump, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"exported -> {OUT_PATH}")


if __name__ == "__main__":
    main()
