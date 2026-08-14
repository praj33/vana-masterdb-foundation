"""Deterministic observation logical identity.

Participating fields (canonical only — no timestamps or arrival time):
  - dataset_id
  - geo_id (nullable)
  - observation_date
  - species (nullable)
  - observation_type
  - confidence (nullable)
  - measurements sorted by (metric_name, value, unit, method)

Identity format: ``OBS-`` + first 32 hex characters of SHA-256 digest.

Synthetic-test alias ``OBSERVATION-001`` is permitted only when the source is
``SYNTHETIC_TEST`` with ``is_synthetic=true`` and the payload matches the fixed
acceptance fixture. The deterministic logical identity is always computed and
validated even when the alias is used.
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

SYNTHETIC_ALIAS_ID = "OBSERVATION-001"
IDENTITY_PREFIX = "OBS-"
IDENTITY_HEX_LEN = 32

_FIXTURE_PATH = Path(__file__).resolve().parents[2] / "fixtures" / "synthetic_observation_001.json"
_SYNTHETIC_FIXTURE: dict[str, Any] | None = None


def _load_synthetic_fixture() -> dict[str, Any]:
    global _SYNTHETIC_FIXTURE
    if _SYNTHETIC_FIXTURE is None:
        with _FIXTURE_PATH.open(encoding="utf-8") as fh:
            _SYNTHETIC_FIXTURE = json.load(fh)
    return _SYNTHETIC_FIXTURE


def _normalize_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float, Decimal)):
        return format(Decimal(str(value)).normalize(), "f")
    return str(value)


def _normalize_measurement(measurement: dict[str, Any]) -> dict[str, str]:
    return {
        "metric_name": _normalize_value(measurement.get("metric_name")),
        "value": _normalize_value(measurement.get("value")),
        "unit": _normalize_value(measurement.get("unit")),
        "method": _normalize_value(measurement.get("method")),
    }


def build_identity_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Extract canonical identity fields from an ingestion payload."""
    observation = payload.get("observation") or {}
    measurements = payload.get("measurements") or []
    dataset = payload.get("dataset") or {}

    normalized_measurements = sorted(
        (_normalize_measurement(m) for m in measurements),
        key=lambda item: (
            item["metric_name"],
            item["value"],
            item["unit"],
            item["method"],
        ),
    )

    return {
        "dataset_id": _normalize_value(dataset.get("dataset_id")),
        "geo_id": _normalize_value(observation.get("geo_id")),
        "observation_date": _normalize_value(observation.get("observation_date")),
        "species": _normalize_value(observation.get("species")),
        "observation_type": _normalize_value(observation.get("observation_type")),
        "confidence": _normalize_value(observation.get("confidence")),
        "measurements": normalized_measurements,
    }


def compute_logical_identity(payload: dict[str, Any]) -> str:
    """Return deterministic logical identity ``OBS-<32 hex chars>``."""
    identity_payload = build_identity_payload(payload)
    canonical = json.dumps(identity_payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"{IDENTITY_PREFIX}{digest[:IDENTITY_HEX_LEN]}"


def participating_fields() -> list[str]:
    """Document the fields that participate in logical identity."""
    return [
        "dataset_id",
        "geo_id (nullable)",
        "observation_date",
        "species (nullable)",
        "observation_type",
        "confidence (nullable)",
        "measurements (sorted by metric_name, value, unit, method)",
    ]


def _payload_matches_synthetic_fixture(payload: dict[str, Any]) -> bool:
    fixture = _load_synthetic_fixture()
    fixture_identity = build_identity_payload(fixture)
    payload_identity = build_identity_payload(payload)
    return fixture_identity == payload_identity


def is_synthetic_alias_allowed(payload: dict[str, Any]) -> bool:
    source = payload.get("source") or {}
    return (
        source.get("source_type") == "SYNTHETIC_TEST"
        and source.get("is_synthetic") is True
        and _payload_matches_synthetic_fixture(payload)
    )


def resolve_observation_id(payload: dict[str, Any]) -> tuple[str, str]:
    """Resolve stored observation id and return (observation_id, logical_identity).

    Raises ``ValueError`` when an alias is requested but not permitted or when
    the alias does not match the computed logical identity contract.
    """
    logical_identity = compute_logical_identity(payload)
    requested_id = payload.get("observation_id")

    if requested_id == SYNTHETIC_ALIAS_ID:
        if not is_synthetic_alias_allowed(payload):
            raise ValueError(
                f"observation_id '{SYNTHETIC_ALIAS_ID}' is only allowed for "
                "SYNTHETIC_TEST sources with is_synthetic=true matching the fixed fixture"
            )
        expected_logical = compute_logical_identity(_load_synthetic_fixture())
        if logical_identity != expected_logical:
            raise ValueError(
                "Synthetic alias payload does not produce the expected logical identity"
            )
        return SYNTHETIC_ALIAS_ID, logical_identity

    if requested_id and requested_id != logical_identity:
        raise ValueError(
            f"Provided observation_id '{requested_id}' does not match "
            f"computed logical identity '{logical_identity}'"
        )

    return logical_identity, logical_identity
