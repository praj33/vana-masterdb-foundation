"""Shared pytest fixtures with real SQLite persistence."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from vana_integrity.api import create_app
from vana_integrity.db import apply_schema, connect, count_observations

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = ROOT / "fixtures" / "synthetic_observation_001.json"


@pytest.fixture
def db_conn() -> sqlite3.Connection:
    conn = connect(":memory:")
    apply_schema(conn)
    yield conn
    conn.close()


@pytest.fixture
def synthetic_payload() -> dict:
    with FIXTURE_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture
def client(db_conn: sqlite3.Connection) -> TestClient:
    app, _conn = create_app(conn=db_conn)
    return TestClient(app)


def observation_count(conn: sqlite3.Connection) -> int:
    return count_observations(conn)
