import json
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "observation.schema.v2.json"


def load_v21_validator() -> Draft202012Validator:
    with SCHEMA_PATH.open("r", encoding="utf-8") as f:
        schema = json.load(f)

    return Draft202012Validator(schema)


def validate_v21_observation(observation: dict) -> list[str]:
    validator = load_v21_validator()

    errors = sorted(
        validator.iter_errors(observation),
        key=lambda error: list(error.path),
    )

    return [
        f"{'/'.join(map(str, error.path)) or '<root>'}: {error.message}"
        for error in errors
    ]
