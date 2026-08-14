"""Validation and partial-write failure mode tests."""

from __future__ import annotations

import copy

from fastapi.testclient import TestClient

from vana_integrity.db import count_measurements, count_observations, count_provenance


def test_malformed_payload_leaves_counts_unchanged(
    client: TestClient,
    db_conn,
    synthetic_payload: dict,
) -> None:
    before_obs = count_observations(db_conn)
    before_meas = count_measurements(db_conn)
    before_prov = count_provenance(db_conn)

    bad = copy.deepcopy(synthetic_payload)
    del bad["measurements"]

    response = client.post("/ingest/observations", json=bad)
    assert response.status_code == 422
    assert count_observations(db_conn) == before_obs
    assert count_measurements(db_conn) == before_meas
    assert count_provenance(db_conn) == before_prov


def test_failed_then_valid_retry_creates_exactly_one(
    client: TestClient,
    db_conn,
    synthetic_payload: dict,
) -> None:
    bad = copy.deepcopy(synthetic_payload)
    bad["source"]["source_type"] = "NOT_A_REAL_TYPE"

    failed = client.post("/ingest/observations", json=bad)
    assert failed.status_code == 422
    assert count_observations(db_conn) == 0

    ok = client.post("/ingest/observations", json=synthetic_payload)
    assert ok.status_code == 201
    assert count_observations(db_conn) == 1

    retry = client.post("/ingest/observations", json=synthetic_payload)
    assert retry.status_code == 200
    assert count_observations(db_conn) == 1
