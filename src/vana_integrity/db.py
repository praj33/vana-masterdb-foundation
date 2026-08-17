"""Database helpers — schema bootstrap and connection management."""

from __future__ import annotations

import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SQLITE_MIGRATION_PATH = ROOT / "migrations" / "0001_init_sqlite.sql"


def connect(database_url: str = ":memory:") -> sqlite3.Connection:
    """Open a SQLite connection with row factory."""
    if database_url.startswith("sqlite:"):
        database_url = database_url.removeprefix("sqlite:")
    conn = sqlite3.connect(database_url, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def apply_schema(conn: sqlite3.Connection) -> None:
    """Apply canonical v0.4 SQLite schema."""
    sql = SQLITE_MIGRATION_PATH.read_text(encoding="utf-8")
    conn.executescript(sql)
    conn.commit()


def count_observations(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COUNT(*) AS c FROM observation").fetchone()
    return int(row["c"])


def count_measurements(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COUNT(*) AS c FROM measurement").fetchone()
    return int(row["c"])


def count_provenance(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COUNT(*) AS c FROM provenance").fetchone()
    return int(row["c"])

