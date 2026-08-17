"""Mandatory acceptance test: 0 → 1 → 1 idempotency proof with real DB counts."""

from __future__ import annotations

import copy

import pytest
from fastapi.testclient import TestClient

from vana_integrity.db import count_observations


def test_acceptance_001_idempotency_proof(
    client: TestClient,
    db_conn,
    synthetic_payload: dict,
) -> None:
    before_count = count_observations(db_conn)
    assert before_count == 0

    headers = {"Idempotency-Key": "acceptance-001-key"}

    first = client.post("/ingest/observations", json=synthetic_payload, headers=headers)
    first_status = first.status_code
    assert first_status == 201
    first_count = count_observations(db_conn)
    assert first_count == 1

    second = client.post("/ingest/observations", json=synthetic_payload, headers=headers)
    second_status = second.status_code
    assert second_status == 200
    second_count = count_observations(db_conn)
    assert second_count == 1

    mutated = copy.deepcopy(synthetic_payload)
    mutated["observation"]["confidence"] = "LOW"
    third = client.post("/ingest/observations", json=mutated, headers=headers)
    assert third.status_code == 409
    third_count = count_observations(db_conn)
    assert third_count == 1

    is_pass = (
        first_status == 201
        and second_status == 200
        and before_count == 0
        and first_count == 1
        and second_count == 1
        and third_count == 1
    )
    result_str = "PASS" if is_pass else "FAIL"

    print(f"FIRST_HTTP_STATUS={first_status}")
    print(f"SECOND_HTTP_STATUS={second_status}")
    print(f"BEFORE_COUNT={before_count}")
    print(f"FIRST_SUBMISSION_COUNT={first_count}")
    print(f"SECOND_SUBMISSION_COUNT={second_count}")
    print(f"RESULT={result_str}")
    print("PROOF=0 -> 1 -> 1")

    if second_count == 2:
        pytest.fail("Idempotency failure: observed 0 -> 1 -> 2")

