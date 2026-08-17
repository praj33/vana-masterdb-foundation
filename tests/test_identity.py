"""Identity contract tests for caller-supplied canonical observation_id."""

from __future__ import annotations

import copy
import pytest

from vana_integrity.identity import (
    participating_fields,
    resolve_observation_id,
)


def test_participating_fields_documented() -> None:
    fields = participating_fields()
    assert any("observation_id" in f for f in fields)


def test_caller_supplied_id_accepted(synthetic_payload: dict) -> None:
    payload = copy.deepcopy(synthetic_payload)
    payload["observation_id"] = "OBSERVATION-001"
    obs_id = resolve_observation_id(payload)
    assert obs_id == "OBSERVATION-001"


def test_group3_id_persisted_verbatim(synthetic_payload: dict) -> None:
    payload = copy.deepcopy(synthetic_payload)
    payload["observation_id"] = "TC-Z03-F02-LIDAR-OBS001"
    obs_id = resolve_observation_id(payload)
    assert obs_id == "TC-Z03-F02-LIDAR-OBS001"


def test_nested_observation_id_supported(synthetic_payload: dict) -> None:
    payload = copy.deepcopy(synthetic_payload)
    del payload["observation_id"]
    payload["observation"]["observation_id"] = "TC-Z03-F02-LIDAR-OBS001"
    obs_id = resolve_observation_id(payload)
    assert obs_id == "TC-Z03-F02-LIDAR-OBS001"


def test_missing_observation_id_raises_value_error(synthetic_payload: dict) -> None:
    payload = copy.deepcopy(synthetic_payload)
    payload.pop("observation_id", None)
    if isinstance(payload.get("observation"), dict):
        payload["observation"].pop("observation_id", None)

    with pytest.raises(ValueError, match="Caller-supplied observation_id is required"):
        resolve_observation_id(payload)


def test_no_obs_hash_generated(synthetic_payload: dict) -> None:
    payload = copy.deepcopy(synthetic_payload)
    payload["observation_id"] = "TC-Z03-F02-LIDAR-OBS001"
    obs_id = resolve_observation_id(payload)
    assert not obs_id.startswith("OBS-")
    assert obs_id == "TC-Z03-F02-LIDAR-OBS001"

