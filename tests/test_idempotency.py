"""Idempotency key and fingerprint behaviour with real DB."""

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


def test_different_observation_increments_count(
    client: TestClient,
    db_conn,
    synthetic_payload: dict,
) -> None:
    client.post("/ingest/observations", json=synthetic_payload)
    assert count_observations(db_conn) == 1

    other = copy.deepcopy(synthetic_payload)
    other.pop("observation_id", None)
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
    client.post("/ingest/observations", json=synthetic_payload, headers=headers)

    mutated = copy.deepcopy(synthetic_payload)
    mutated["observation"]["confidence"] = "LOW"
    conflict = client.post("/ingest/observations", json=mutated, headers=headers)
    assert conflict.status_code == 409
    assert count_observations(db_conn) == 1
