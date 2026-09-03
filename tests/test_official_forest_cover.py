import copy
import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


TEST_DB = Path(__file__).resolve().parents[1] / "test_vana_official_api.db"

import api.db
from api.db import initialize_database
from api.main import app


client = TestClient(app)
FIXTURE = Path(__file__).resolve().parents[1] / "sample_fsi_isfr_2023_forest_cover.json"


@pytest.fixture(autouse=True)
def reset_database(monkeypatch):
    monkeypatch.setattr(api.db, "DB_URL", f"sqlite:///{TEST_DB}")
    if TEST_DB.exists():
        TEST_DB.unlink()
    initialize_database()
    yield
    if TEST_DB.exists():
        TEST_DB.unlink()


def payload():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_valid_official_record_preserves_null_unavailable_values():
    response = client.post("/official/forest-cover", json=payload())

    assert response.status_code == 201
    record_id = response.json()["record_id"]
    retrieved = client.get(f"/official/forest-cover/{record_id}")

    assert retrieved.status_code == 200
    record = retrieved.json()
    assert record["assessment_year"] == 2023
    assert record["state"] == "Maharashtra"
    assert record["forest_cover_area"] is None
    assert record["source"]["source_name"] == "Forest Survey of India"

    conn = sqlite3.connect(TEST_DB)
    counts = conn.execute(
        "SELECT (SELECT COUNT(*) FROM observation), (SELECT COUNT(*) FROM official_forest_cover_record)"
    ).fetchone()
    conn.close()
    assert counts == (0, 1)


def test_historical_assessment_year_is_preserved():
    record = payload()
    record["assessment_year"] = 2001
    record["source_record_id"] = "TEST-ROW-2001"
    record["idempotency_key"] = "IK-FSI-ISFR-2001-TEST-ROW-2001"

    response = client.post("/official/forest-cover", json=record)

    assert response.status_code == 201
    assert client.get(f"/official/forest-cover/{response.json()['record_id']}").json()["assessment_year"] == 2001


def test_missing_provenance_is_rejected():
    record = payload()
    del record["provenance_reference"]

    response = client.post("/official/forest-cover", json=record)

    assert response.status_code == 422


def test_invalid_geography_is_rejected():
    record = payload()
    record["geography_level"] = "COUNTY"

    response = client.post("/official/forest-cover", json=record)

    assert response.status_code == 400
    assert "geography_level must be STATE or DISTRICT" in response.json()["detail"]


def test_duplicate_identical_ingestion_replays():
    first = client.post("/official/forest-cover", json=payload())
    second = client.post("/official/forest-cover", json=payload())

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json()["record_id"] == first.json()["record_id"]


def test_duplicate_conflicting_ingestion_is_rejected():
    first = client.post("/official/forest-cover", json=payload())
    conflicting = payload()
    conflicting["state"] = "Gujarat"

    second = client.post("/official/forest-cover", json=conflicting)

    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json()["status"] == "CONFLICT"


def test_district_requires_district_and_does_not_create_point_geometry():
    record = payload()
    record["geography_level"] = "DISTRICT"
    record["district"] = "Test District"
    record["source_record_id"] = "TEST-DISTRICT-001"
    record["idempotency_key"] = "IK-FSI-ISFR-2023-TEST-DISTRICT-001"

    response = client.post("/official/forest-cover", json=record)

    assert response.status_code == 201
    conn = sqlite3.connect(TEST_DB)
    official_count = conn.execute("SELECT COUNT(*) FROM official_forest_cover_record").fetchone()[0]
    geo_count = conn.execute("SELECT COUNT(*) FROM geo_location").fetchone()[0]
    conn.close()
    assert official_count == 1
    assert geo_count == 0


def test_official_record_is_not_interpreted_as_group3_observation():
    response = client.post("/official/forest-cover", json=payload())
    record_id = response.json()["record_id"]

    assert client.get(f"/observations/{record_id}").status_code == 404


def test_group3_observation_endpoint_remains_available():
    group3 = json.loads(
        (Path(__file__).resolve().parents[1] / "sample_mission_package.v2.2.json").read_text(encoding="utf-8")
    )["observations"][0]

    response = client.post("/observations", json=group3)

    assert response.status_code == 201