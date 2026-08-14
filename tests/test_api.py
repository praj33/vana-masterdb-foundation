import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import app, _observation_store


ROOT = Path(__file__).resolve().parents[1]
client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_store():
    _observation_store.clear()
    yield
    _observation_store.clear()


def load_observations():
    with (ROOT / "sample_mission_package.json").open(
        "r", encoding="utf-8"
    ) as f:
        return json.load(f)["observations"]


def test_health():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_valid_observation_is_accepted():
    observation = load_observations()[0]

    response = client.post("/observations", json=observation)

    assert response.status_code == 201
    assert response.json()["observation_id"] == observation["observation_id"]
    assert response.json()["status"] == "ACCEPTED"


def test_observation_can_be_retrieved():
    observation = load_observations()[1]

    response = client.post("/observations", json=observation)
    assert response.status_code == 201

    retrieved = client.get(
        f"/observations/{observation['observation_id']}"
    )

    assert retrieved.status_code == 200
    assert retrieved.json()["status"] == "RETRIEVED"
    assert retrieved.json()["observation"] == observation


def test_invalid_observation_is_rejected():
    observation = load_observations()[0].copy()
    del observation["timestamp"]

    response = client.post("/observations", json=observation)

    assert response.status_code == 400
    assert response.json()["status"] == "REJECTED"
    assert response.json()["errors"]


def test_duplicate_observation_is_detected():
    observation = load_observations()[2]

    first = client.post("/observations", json=observation)
    second = client.post("/observations", json=observation)

    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json()["status"] == "DUPLICATE"


def test_missing_observation_returns_404():
    response = client.get("/observations/DOES-NOT-EXIST")

    assert response.status_code == 404
    assert response.json()["status"] == "NOT_FOUND"

def test_uncertain_observation_with_null_coordinates_is_accepted():
    observation = load_observations()[2]

    response = client.post("/observations", json=observation)

    assert response.status_code == 201
    assert response.json()["status"] == "ACCEPTED"


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
