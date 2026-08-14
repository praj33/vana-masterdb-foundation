import os
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

DB_URL = os.environ.get(
    "VANA_DATABASE_URL",
    "sqlite:///vana_api.db",
)


def get_connection():
    """
    Open the configured VANA database.

    SQLite is used for local deterministic API/persistence tests.
    PostgreSQL is the deployment/VM target.
    """
    if DB_URL.startswith("sqlite:///"):
        path = DB_URL.replace("sqlite:///", "", 1)

        conn = sqlite3.connect(
            path,
            check_same_thread=False,
        )
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    if DB_URL.startswith("postgresql://") or DB_URL.startswith("postgres://"):
        try:
            import psycopg2
        except ImportError as exc:
            raise RuntimeError(
                "PostgreSQL backend requires psycopg2-binary."
            ) from exc

        return psycopg2.connect(DB_URL)

    raise RuntimeError(
        f"Unsupported VANA_DATABASE_URL: {DB_URL}"
    )


def initialize_database() -> None:
    """
    Initialize the locked VANA v0.4 schema.
    """
    if DB_URL.startswith("sqlite:///"):
        migration_path = ROOT / "migrations" / "0001_init_sqlite.sql"
    else:
        migration_path = ROOT / "migrations" / "0001_init.sql"

    sql = migration_path.read_text(encoding="utf-8")
    conn = get_connection()

    try:
        if DB_URL.startswith("sqlite:///"):
            conn.executescript(sql)
            conn.commit()
        else:
            with conn.cursor() as cursor:
                cursor.execute(sql)
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
