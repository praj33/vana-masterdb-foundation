import json
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "observation.schema.json"


def load_validator() -> Draft202012Validator:
    with SCHEMA_PATH.open("r", encoding="utf-8") as f:
        schema = json.load(f)

    return Draft202012Validator(schema)


def _strip_fixture_metadata(observation: dict) -> dict:
    """Remove underscore-prefixed fixture metadata before contract validation."""
    return {
        key: value
        for key, value in observation.items()
        if not key.startswith("_")
    }


def validate_observation(observation: dict) -> list[str]:
    """
    Validate one Group 3 observation against the frozen V1.0 contract.

    Returns an empty list when valid, otherwise deterministic
    validation error messages.
    """
    validator = load_validator()
    clean_observation = _strip_fixture_metadata(observation)

    errors = sorted(
        validator.iter_errors(clean_observation),
        key=lambda error: list(error.path),
    )

    return [
        f"{'/'.join(map(str, error.path)) or '<root>'}: {error.message}"
        for error in errors
    ]