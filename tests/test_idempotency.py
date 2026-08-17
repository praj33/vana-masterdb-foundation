"""Idempotency key and fingerprint behavior tests with idempotency_record table."""

from __future__ import annotations

import copy

from fastapi.testclient import TestClient

from vana_integrity.db import count_observations


def test_first_submission_zero_to_one(
    client: TestClient,
    db_conn,
    synthetic_payload: dict,
) -> None:
    assert count_observations(db_conn) == 0
    response = client.post("/ingest/observations", json=synthetic_payload)
    assert response.status_code == 201
    assert count_observations(db_conn) == 1


def test_exact_duplicate_stays_one(
    client: TestClient,
    db_conn,
    synthetic_payload: dict,
) -> None:
    client.post("/ingest/observations", json=synthetic_payload)
    assert count_observations(db_conn) == 1
    duplicate = client.post("/ingest/observations", json=synthetic_payload)
    assert duplicate.status_code == 200
    assert count_observations(db_conn) == 1


def test_request_retry_with_idempotency_key(
    client: TestClient,
    db_conn,
    synthetic_payload: dict,
) -> None:
    headers = {"Idempotency-Key": "retry-key-001"}
    first = client.post("/ingest/observations", json=synthetic_payload, headers=headers)
    second = client.post("/ingest/observations", json=synthetic_payload, headers=headers)
    assert first.status_code == 201
    assert second.status_code == 200
    assert count_observations(db_conn) == 1

    # Verify idempotency_record table entry
    row = db_conn.execute(
        "SELECT * FROM idempotency_record WHERE idempotency_key = 'retry-key-001'"
    ).fetchone()
    assert row is not None
    assert row["observation_id"] == "OBSERVATION-001"
    assert row["fingerprint_algorithm"] == "sha256"
    assert row["first_response_status"] == "201"


def test_different_observation_increments_count(
    client: TestClient,
    db_conn,
    synthetic_payload: dict,
) -> None:
    client.post("/ingest/observations", json=synthetic_payload)
    assert count_observations(db_conn) == 1

    other = copy.deepcopy(synthetic_payload)
    other["observation_id"] = "OBSERVATION-002"
    other["observation"]["observation_id"] = "OBSERVATION-002"
    other["dataset"]["dataset_id"] = "DS-SYNTHETIC-OTHER-002"
    other["source"]["source_id"] = "SRC-SYNTHETIC-OTHER-002"
    other["observation"]["observation_type"] = "BIOMASS"

    response = client.post("/ingest/observations", json=other)
    assert response.status_code == 201
    assert count_observations(db_conn) == 2


def test_same_key_different_body_returns_409(
    client: TestClient,
    db_conn,
    synthetic_payload: dict,
) -> None:
    headers = {"Idempotency-Key": "conflict-key"}
    first = client.post("/ingest/observations", json=synthetic_payload, headers=headers)
    assert first.status_code == 201

    mutated = copy.deepcopy(synthetic_payload)
    mutated["observation"]["confidence"] = "LOW"
    conflict = client.post("/ingest/observations", json=mutated, headers=headers)
    assert conflict.status_code == 409
    assert count_observations(db_conn) == 1

    # Verify original observation remains unchanged
    row = db_conn.execute("SELECT confidence FROM observation WHERE observation_id = 'OBSERVATION-001'").fetchone()
    assert row["confidence"] == "HIGH"

