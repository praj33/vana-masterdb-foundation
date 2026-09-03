#!/usr/bin/env python3
"""
init_db.py — VANA database init / migration runner.

Reproducible setup command:
    python3 init_db.py

Reads VANA_DATABASE_URL (falls back to sqlite:///vana.db if unset —
same env-var-driven-backend discipline as MasterDB's
MASTERDB_DATABASE_URL, applied to VANA).

On a real deployment this should point at Postgres, e.g.:
    export VANA_DATABASE_URL="postgresql://user:pass@vm-host:5432/vana"
and be run with psycopg2 installed. This sandbox has no network to
reach a real Postgres instance or install psycopg2, so this runner's
Postgres path is written but not executed here — only the SQLite path
is actually run and proven in this session (see EVIDENCE.txt). The
SQL in migrations/0001_init.sql is the literal statement to run on
Postgres; nothing in it is sandbox-specific.

Tracks applied migrations in a `_migrations_log` table so re-running
this command is a no-op after the first successful run (idempotent
setup, not just idempotent data writes).
"""

import os
import sys
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

MIGRATIONS_DIR = Path(__file__).parent / "migrations"
DB_URL = os.environ.get("VANA_DATABASE_URL", "sqlite:///vana.db")


def now():
    return datetime.now(timezone.utc).isoformat()


def get_sqlite_path(url):
    assert url.startswith("sqlite:///"), url
    return url.replace("sqlite:///", "", 1)


def run_sqlite(url):
    db_path = get_sqlite_path(url)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS _migrations_log (
            filename TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
    """)
    applied = {r[0] for r in conn.execute("SELECT filename FROM _migrations_log")}

    migration_file = MIGRATIONS_DIR / "0001_init_sqlite.sql"
    if migration_file.name in applied:
        print(f"[init_db] {migration_file.name} already applied — nothing to do.")
    else:
        sql = migration_file.read_text()
        conn.executescript(sql)
        conn.execute(
            "INSERT INTO _migrations_log (filename, applied_at) VALUES (?, ?)",
            (migration_file.name, now()),
        )
        conn.execute(
            "INSERT OR IGNORE INTO schema_version (version, applied_at, description) VALUES (?, ?, ?)",
            ("0.3", now(), "geo_location rename, field_observation_meta, raw_artifact, observed_at, capture_method, measurement.data_type"),
        )
        conn.execute(
            "INSERT OR IGNORE INTO schema_version (version, applied_at, description) VALUES (?, ?, ?)",
            ("0.4", now(), "idempotency_record: Idempotency-Key + request-fingerprint contract"),
        )
        conn.execute(
            "INSERT OR IGNORE INTO schema_version (version, applied_at, description) VALUES (?, ?, ?)",
            ("0.5", now(), "field_observation_meta.accuracy_status, CHECK constraint on capture_method"),
        )
        conn.execute(
            "INSERT OR IGNORE INTO schema_version (version, applied_at, description) VALUES (?, ?, ?)",
            ("0.6", now(), "geo_location.altitude_m, field_observation_meta.gnss_status/position_accuracy_m, provenance now supports artifact-only observations"),
        )
        conn.execute(
            "INSERT OR IGNORE INTO schema_version (version, applied_at, description) VALUES (?, ?, ?)",
            ("0.7", now(), "observation.is_synthetic"),
        )
        conn.execute(
            "INSERT OR IGNORE INTO schema_version (version, applied_at, description) VALUES (?, ?, ?)",
            ("0.8", now(), "observation.synthetic_state (5-state model, V2.2), is_synthetic retained as compatibility field"),
        )
        conn.commit()
        print(f"[init_db] Applied {migration_file.name} — VANA schema v0.8 ready.")

    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    print(f"[init_db] Tables present: {[t[0] for t in tables]}")
    conn.close()
    return db_path


def run_postgres(url):
    # Real path for the VM. Not executed in this sandbox (no network,
    # no psycopg2 available) — written so it's ready to run as-is.
    try:
        import psycopg2
    except ImportError:
        print("[init_db] psycopg2 not installed in this environment — "
              "this path is for the real VM run, not this sandbox.")
        sys.exit(1)

    conn = psycopg2.connect(url)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS _migrations_log (
            filename TEXT PRIMARY KEY,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    cur.execute("SELECT filename FROM _migrations_log")
    applied = {r[0] for r in cur.fetchall()}

    sql_files = sorted([f for f in MIGRATIONS_DIR.glob("000*.sql") if not f.name.endswith("_sqlite.sql")])
    for migration_file in sql_files:
        if migration_file.name in applied:
            print(f"[init_db] {migration_file.name} already applied — skipping.")
        else:
            sql = migration_file.read_text()
            cur.execute(sql)
            cur.execute("INSERT INTO _migrations_log (filename) VALUES (%s)", (migration_file.name,))
            print(f"[init_db] Applied {migration_file.name}.")

    cur.execute("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema='public' ORDER BY table_name
    """)
    print(f"[init_db] Tables present: {[r[0] for r in cur.fetchall()]}")
    conn.close()


if __name__ == "__main__":
    print(f"[init_db] VANA_DATABASE_URL = {DB_URL}")
    if DB_URL.startswith("sqlite:///"):
        run_sqlite(DB_URL)
    elif DB_URL.startswith("postgresql://") or DB_URL.startswith("postgres://"):
        run_postgres(DB_URL)
    else:
        print(f"[init_db] Unrecognized DB URL scheme: {DB_URL}")
        sys.exit(1)
