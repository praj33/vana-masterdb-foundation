"""Identity computation and synthetic alias tests."""

from __future__ import annotations

import copy
import json

import pytest

from vana_integrity.identity import (
    SYNTHETIC_ALIAS_ID,
    build_identity_payload,
    compute_logical_identity,
    is_synthetic_alias_allowed,
    participating_fields,
    resolve_observation_id,
)


def test_participating_fields_documented() -> None:
    fields = participating_fields()
    assert "dataset_id" in fields
    assert "measurements (sorted by metric_name, value, unit, method)" in fields


def test_logical_identity_is_deterministic(synthetic_payload: dict) -> None:
    first = compute_logical_identity(synthetic_payload)
    second = compute_logical_identity(copy.deepcopy(synthetic_payload))
    assert first == second
    assert first.startswith("OBS-")
    assert len(first) == len("OBS-") + 32


def test_measurement_ordering_affects_identity(synthetic_payload: dict) -> None:
    payload_a = copy.deepcopy(synthetic_payload)
    payload_b = copy.deepcopy(synthetic_payload)
    payload_b["measurements"] = list(reversed(payload_b["measurements"]))
    assert compute_logical_identity(payload_a) == compute_logical_identity(payload_b)


def test_synthetic_alias_allowed_for_fixture(synthetic_payload: dict) -> None:
    assert is_synthetic_alias_allowed(synthetic_payload) is True
    obs_id, logical = resolve_observation_id(synthetic_payload)
    assert obs_id == SYNTHETIC_ALIAS_ID
    assert logical.startswith("OBS-")


def test_synthetic_alias_rejected_for_non_synthetic(synthetic_payload: dict) -> None:
    payload = copy.deepcopy(synthetic_payload)
    payload["source"]["source_type"] = "INSTITUTIONAL"
    payload["source"]["is_synthetic"] = False
    with pytest.raises(ValueError):
        resolve_observation_id(payload)


def test_identity_excludes_timestamps(synthetic_payload: dict) -> None:
    identity_payload = build_identity_payload(synthetic_payload)
    serialized = json.dumps(identity_payload)
    assert "created_at" not in serialized
    assert "retrieved_at" not in serialized
