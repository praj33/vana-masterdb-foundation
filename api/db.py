import os
import sqlite3
from pathlib import Path
from urllib.parse import urlparse, urlunparse, quote

ROOT = Path(__file__).resolve().parents[1]

DB_URL = os.environ.get(
    "VANA_DATABASE_URL",
    "sqlite:///vana_api.db",
)


def _safe_pg_url(url: str) -> str:
    """
    Re-encode the password component of a PostgreSQL URL so that
    special characters (@ # % etc.) in the password do not break
    the URL parser.  psycopg2.connect() receives the sanitised URL.
    """
    parsed = urlparse(url)
    if parsed.password:
        safe_password = quote(parsed.password, safe="")
        # Rebuild netloc with the encoded password
        userinfo = f"{parsed.username}:{safe_password}"
        host_part = parsed.hostname
        if parsed.port:
            host_part = f"{host_part}:{parsed.port}"
        safe_netloc = f"{userinfo}@{host_part}"
        parsed = parsed._replace(netloc=safe_netloc)
    return urlunparse(parsed)


class VANACursor:
    def __init__(self, raw_cursor, is_postgres: bool):
        self._cursor = raw_cursor
        self.is_postgres = is_postgres

    def execute(self, sql: str, params=()):
        if self.is_postgres:
            sql = sql.replace("?", "%s")
        return self._cursor.execute(sql, params)

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()


class VANAConn:
    def __init__(self, raw_conn, is_postgres: bool):
        self.raw_conn = raw_conn
        self.is_postgres = is_postgres

    def cursor(self):
        return VANACursor(self.raw_conn.cursor(), self.is_postgres)

    def execute(self, sql: str, params=()):
        cur = self.cursor()
        cur.execute(sql, params)
        return cur

    def commit(self):
        self.raw_conn.commit()

    def rollback(self):
        self.raw_conn.rollback()

    def close(self):
        self.raw_conn.close()


def get_connection() -> VANAConn:
    """
    Open the configured VANA database wrapper.

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
        return VANAConn(conn, is_postgres=False)

    if DB_URL.startswith("postgresql://") or DB_URL.startswith("postgres://"):
        try:
            import psycopg2
        except ImportError as exc:
            raise RuntimeError(
                "PostgreSQL backend requires psycopg2-binary."
            ) from exc

        conn = psycopg2.connect(_safe_pg_url(DB_URL))
        return VANAConn(conn, is_postgres=True)

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

    sql = migration_path.read_text(encoding="utf-8").lstrip("\ufeff")
    conn = get_connection()

    try:
        if DB_URL.startswith("sqlite:///"):
            conn.raw_conn.executescript(sql)
            conn.commit()
        else:
            with conn.raw_conn.cursor() as cursor:
                cursor.execute(sql)
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

