import json
import os
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


# Use a dedicated SQLite database for API integration tests.
TEST_DB = Path(__file__).resolve().parents[1] / "test_vana_api.db"
os.environ["VANA_DATABASE_URL"] = f"sqlite:///{TEST_DB}"


from api.db import initialize_database
from api.main import app


ROOT = Path(__file__).resolve().parents[1]
client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_database():
    if TEST_DB.exists():
        TEST_DB.unlink()

    initialize_database()

    yield

    if TEST_DB.exists():
        TEST_DB.unlink()


def load_observations():
    with (ROOT / "sample_mission_package.json").open(
        "r",
        encoding="utf-8",
    ) as f:
        return json.load(f)["observations"]


def test_health():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_valid_observation_is_persisted():
    observation = load_observations()[0]

    response = client.post(
        "/observations",
        json=observation,
    )

    assert response.status_code == 201
    assert response.json()["observation_id"] == observation["observation_id"]
    assert response.json()["status"] == "ACCEPTED"

    conn = sqlite3.connect(TEST_DB)

    row = conn.execute(
        """
        SELECT observation_id
        FROM observation
        WHERE observation_id = ?
        """,
        (observation["observation_id"],),
    ).fetchone()

    conn.close()

    assert row is not None
    assert row[0] == observation["observation_id"]


def test_observation_can_be_retrieved_from_canonical_persistence():
    observation = load_observations()[1]

    response = client.post(
        "/observations",
        json=observation,
    )

    assert response.status_code == 201

    retrieved = client.get(
        f"/observations/{observation['observation_id']}"
    )

    assert retrieved.status_code == 200
    assert retrieved.json()["status"] == "RETRIEVED"

    persisted = retrieved.json()["observation"]

    assert persisted["observation_id"] == observation["observation_id"]
    assert persisted["observed_at"] == observation["timestamp"]
    assert persisted["observation_type"] == observation["observation_type"]


def test_invalid_observation_is_rejected():
    observation = load_observations()[0].copy()
    del observation["timestamp"]

    response = client.post(
        "/observations",
        json=observation,
    )

    assert response.status_code == 400
    assert response.json()["status"] == "REJECTED"
    assert response.json()["errors"]


def test_duplicate_observation_is_idempotent_replay():
    observation = load_observations()[2]

    first = client.post(
        "/observations",
        json=observation,
    )

    second = client.post(
        "/observations",
        json=observation,
    )

    assert first.status_code == 201
    assert first.json()["status"] == "ACCEPTED"

    assert second.status_code == 200
    assert second.json()["status"] == "IDEMPOTENT_REPLAY"

    assert (
        second.json()["observation_id"]
        == observation["observation_id"]
    )


def test_idempotent_replay_returns_200():
    observation = load_observations()[0]

    first = client.post(
        "/observations",
        json=observation,
    )

    second = client.post(
        "/observations",
        json=observation,
    )

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json()["status"] == "IDEMPOTENT_REPLAY"
    assert (
        second.json()["observation_id"]
        == observation["observation_id"]
    )


def test_idempotency_conflict_is_rejected():
    observation = load_observations()[0].copy()

    first = client.post(
        "/observations",
        json=observation,
    )

    assert first.status_code == 201

    conflicting = observation.copy()
    conflicting["measurement"] = 999.9

    second = client.post(
        "/observations",
        json=conflicting,
    )

    assert second.status_code == 409
    assert second.json()["status"] == "IDEMPOTENCY_CONFLICT"


def test_missing_observation_returns_404():
    response = client.get(
        "/observations/DOES-NOT-EXIST"
    )

    assert response.status_code == 404
    assert response.json()["status"] == "NOT_FOUND"


def test_uncertain_observation_with_null_coordinates_is_accepted():
    observation = load_observations()[2]

    response = client.post(
        "/observations",
        json=observation,
    )

    assert response.status_code == 201
    assert response.json()["status"] == "ACCEPTED"

    conn = sqlite3.connect(TEST_DB)

    row = conn.execute(
        """
        SELECT geo_id, quality_status
        FROM observation
        WHERE observation_id = ?
        """,
        (observation["observation_id"],),
    ).fetchone()

    conn.close()

    assert row is not None
    assert row[0] is None
    assert row[1] == "UNCERTAIN"


def test_not_verified_accuracy_is_accepted():
    observation = load_observations()[0].copy()

    assert observation["accuracy"] == "NOT VERIFIED"

    response = client.post(
        "/observations",
        json=observation,
    )

    assert response.status_code == 201


def test_missing_raw_artifact_reference_is_rejected():
    observation = load_observations()[0].copy()
    del observation["raw_artifact_reference"]

    response = client.post(
        "/observations",
        json=observation,
    )

    assert response.status_code == 400
    assert response.json()["status"] == "REJECTED"
    assert response.json()["errors"]


def test_missing_provenance_is_rejected():
    observation = load_observations()[0].copy()
    del observation["provenance"]

    response = client.post(
        "/observations",
        json=observation,
    )

    assert response.status_code == 400
    assert response.json()["status"] == "REJECTED"


def test_malformed_observation_id_is_rejected():
    observation = load_observations()[0].copy()
    observation["observation_id"] = "not-an-id"

    response = client.post(
        "/observations",
        json=observation,
    )

    assert response.status_code == 400
    assert response.json()["status"] == "REJECTED"


def test_unexpected_field_is_rejected():
    observation = load_observations()[0].copy()
    observation["injected_field"] = "x"

    response = client.post(
        "/observations",
        json=observation,
    )

    assert response.status_code == 400
    assert response.json()["status"] == "REJECTED"


def test_acceptance_001_idempotency_proof_header():
    observation = load_observations()[0].copy()
    del observation["idempotency_key"]
    headers = {"Idempotency-Key": "test-key-acceptance-001"}

    conn = sqlite3.connect(TEST_DB)
    before_count = conn.execute("SELECT COUNT(*) FROM observation").fetchone()[0]
    conn.close()
    assert before_count == 0

    first = client.post("/observations", json=observation, headers=headers)
    assert first.status_code == 201
    assert first.json()["status"] == "ACCEPTED"

    conn = sqlite3.connect(TEST_DB)
    first_count = conn.execute("SELECT COUNT(*) FROM observation").fetchone()[0]
    conn.close()
    assert first_count == 1

    second = client.post("/observations", json=observation, headers=headers)
    assert second.status_code == 200
    assert second.json()["status"] == "IDEMPOTENT_REPLAY"

    conn = sqlite3.connect(TEST_DB)
    second_count = conn.execute("SELECT COUNT(*) FROM observation").fetchone()[0]
    conn.close()
    assert second_count == 1

    mutated = observation.copy()
    mutated["quality_status"] = "UNCERTAIN"
    third = client.post("/observations", json=mutated, headers=headers)
    assert third.status_code == 409
    assert third.json()["status"] == "IDEMPOTENCY_CONFLICT"

    conn = sqlite3.connect(TEST_DB)
    third_count = conn.execute("SELECT COUNT(*) FROM observation").fetchone()[0]
    conn.close()
    assert third_count == 1


def test_duplicate_submission_without_key_returns_409_duplicate():
    observation = load_observations()[0].copy()
    observation["observation_id"] = "TC-Z03-F02-LIDAR-OBS099"
    if "idempotency_key" in observation:
        del observation["idempotency_key"]

    first = client.post("/observations", json=observation)
    assert first.status_code == 201

    second = client.post("/observations", json=observation)
    assert second.status_code == 409
    assert second.json()["status"] == "DUPLICATE"


def test_deterministic_child_ids_and_decision_d_mapping():
    observation = load_observations()[0].copy()
    observation["observation_id"] = "TC-Z03-F02-LIDAR-OBS088"
    observation["idempotency_key"] = "key-det-001"

    res = client.post("/observations", json=observation)
    assert res.status_code == 201

    retrieved = client.get("/observations/TC-Z03-F02-LIDAR-OBS088")
    assert retrieved.status_code == 200
    data = retrieved.json()["observation"]

    assert data["capture_method"] == "aerial"
    assert data["observation_type"] == "canopy_height"

    conn = sqlite3.connect(TEST_DB)
    meas = conn.execute("SELECT measurement_id FROM measurement WHERE observation_id = ?", ("TC-Z03-F02-LIDAR-OBS088",)).fetchone()
    art = conn.execute("SELECT artifact_id FROM raw_artifact WHERE observation_id = ?", ("TC-Z03-F02-LIDAR-OBS088",)).fetchone()
    run = conn.execute("SELECT run_id FROM processing_run WHERE output_ref = ?", ("TC-Z03-F02-LIDAR-OBS088",)).fetchone()
    prov = conn.execute("SELECT provenance_id FROM provenance WHERE measurement_id = ?", (meas[0],)).fetchone()
    conn.close()

    assert meas[0].startswith("MEAS-")
    assert art[0].startswith("ART-")
    assert run[0].startswith("RUN-")
    assert prov[0].startswith("PROV-")


