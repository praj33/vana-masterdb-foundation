import json
from pathlib import Path

from api.adapters import adapt_v21_to_canonical
from api.validation_v21 import validate_v21_observation


ROOT = Path(__file__).resolve().parents[1]


def load_v21_observation():
    with (ROOT / "sample_group3_v21.json").open(
        "r", encoding="utf-8-sig"
    ) as f:
        return json.load(f)


def test_v21_fixture_is_valid():
    observation = load_v21_observation()

    assert validate_v21_observation(observation) == []


def test_v21_identity_is_preserved():
    observation = load_v21_observation()
    canonical = adapt_v21_to_canonical(observation)

    assert canonical["observation_id"] == observation["observation_id"]


def test_v21_canonical_field_mappings():
    observation = load_v21_observation()
    canonical = adapt_v21_to_canonical(observation)

    assert canonical["capture_method"] == observation["capture_method"]
    assert canonical["quality_status"] == observation["quality_state"]
    assert canonical["calibration_status"] == observation["calibration_state"]


def test_v21_measurement_is_preserved():
    observation = load_v21_observation()
    canonical = adapt_v21_to_canonical(observation)

    assert canonical["parameter"] == observation["measurement"]["parameter"]
    assert canonical["measurement"] == observation["measurement"]["value"]
    assert canonical["unit"] == observation["unit"]


def test_v21_location_is_preserved():
    observation = load_v21_observation()
    canonical = adapt_v21_to_canonical(observation)

    assert canonical["latitude"] == observation["location"]["latitude"]
    assert canonical["longitude"] == observation["location"]["longitude"]


def test_v21_provenance_artifact_is_preserved():
    observation = load_v21_observation()
    canonical = adapt_v21_to_canonical(observation)

    assert (
        canonical["raw_artifact_sha256"]
        == observation["raw_artifact_integrity"]["checksum_sha256"]
    )


def test_v21_deferred_fields_are_not_promoted():
    observation = load_v21_observation()
    canonical = adapt_v21_to_canonical(observation)

    assert "tidal_state" not in canonical

    context = canonical["v21_context"]

    assert context["is_synthetic"] is True
    assert (
        context["location"]["position_accuracy_m"]
        == observation["location"]["position_accuracy_m"]
    )
    assert (
        context["location"]["altitude_m"]
        == observation["location"]["altitude_m"]
    )
    assert (
        context["location"]["gnss_status"]
        == observation["location"]["gnss_status"]
    )
