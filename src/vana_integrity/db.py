"""Database helpers — schema bootstrap and connection management."""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "schema (1).sql"
MIGRATION_PATH = ROOT / "migrations" / "001_ingestion_idempotency.sql"


def _adapt_schema_for_sqlite(sql: str) -> str:
    """Translate Postgres/PostGIS DDL to SQLite-compatible DDL for tests."""
    lines: list[str] = []
    for line in sql.splitlines():
        stripped = line.strip()
        if stripped.startswith("CREATE EXTENSION"):
            continue
        if "GEOMETRY(Geometry, 4326)" in line:
            line = re.sub(
                r"GEOMETRY\(Geometry,\s*4326\)\s*NOT NULL",
                "TEXT",
                line,
            )
        if stripped.startswith("CREATE INDEX") and "USING GIST" in line:
            line = line.replace("USING GIST (geom)", "(geom)")
        if "ON CONFLICT (version) DO NOTHING" in line:
            line = line.replace("ON CONFLICT (version) DO NOTHING", "ON CONFLICT DO NOTHING")
        if "TIMESTAMPTZ" in line:
            line = line.replace("TIMESTAMPTZ", "TEXT")
        if "observation_date" in line and "DATE" in line:
            line = line.replace("DATE", "TEXT")
        if "NUMERIC" in line:
            line = line.replace("NUMERIC", "REAL")
        if "BOOLEAN" in line:
            line = line.replace("BOOLEAN", "INTEGER")
        if "DEFAULT now()" in line:
            line = line.replace("DEFAULT now()", "DEFAULT CURRENT_TIMESTAMP")
        if "DEFAULT FALSE" in line:
            line = line.replace("DEFAULT FALSE", "DEFAULT 0")
        lines.append(line)
    return "\n".join(lines)


def connect(database_url: str = ":memory:") -> sqlite3.Connection:
    """Open a SQLite connection with row factory."""
    if database_url.startswith("sqlite:"):
        database_url = database_url.removeprefix("sqlite:")
    conn = sqlite3.connect(database_url, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def apply_schema(conn: sqlite3.Connection) -> None:
    """Apply canonical schema and idempotency migration."""
    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    migration_sql = MIGRATION_PATH.read_text(encoding="utf-8")
    adapted = _adapt_schema_for_sqlite(schema_sql)
    adapted_migration = _adapt_schema_for_sqlite(migration_sql)
    conn.executescript(adapted)
    conn.executescript(adapted_migration)
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
