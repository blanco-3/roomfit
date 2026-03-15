from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DatabaseConfig:
    engine: str
    database: str


def parse_database_url(database_url: str) -> DatabaseConfig:
    """Parse minimal DB URL forms.

    Supported now:
    - sqlite:///absolute/or/relative/path.db
    - sqlite:///:memory:
    - postgres* URLs are recognized for forward compatibility but not enabled yet.
    """
    url = database_url.strip()
    if url.startswith("sqlite:///"):
        return DatabaseConfig(engine="sqlite", database=url.removeprefix("sqlite:///"))
    if url.startswith("postgresql://") or url.startswith("postgres://"):
        return DatabaseConfig(engine="postgres", database=url)
    raise ValueError("Unsupported DATABASE_URL. Use sqlite:///... or postgresql://...")


class SQLiteBackend:
    def __init__(self, db_path: Path):
        self.db_path = db_path

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn


class PostgresBackendNotImplemented:
    def __init__(self, dsn: str):
        self.dsn = dsn

    def connect(self):
        raise RuntimeError(
            "Postgres backend scaffold is configured but not enabled yet. "
            "Set DATABASE_URL=sqlite:///... for now."
        )
