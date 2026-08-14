"""Ingestion payload validation."""

from __future__ import annotations

from typing import Any

VALID_SOURCE_TYPES = {
    "SCIENTIFIC_LITERATURE",
    "GOVERNMENT_DATASET",
    "EARTH_OBSERVATION",
    "INSTITUTIONAL",
    "SYNTHETIC_TEST",
}
VALID_CONFIDENCE = {"HIGH", "MEDIUM", "LOW", "UNCERTAIN"}
VALID_PIPELINE_STAGES = {
    "EXTRACT",
    "NORMALISE",
    "CONTEXTUALISE",
    "VALIDATE",
    "PROVENANCE",
    "INGEST",
}


class ValidationError(Exception):
    """Raised when an ingestion payload fails validation."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("; ".join(errors))


def validate_ingestion_payload(payload: dict[str, Any]) -> None:
    errors: list[str] = []

    if not isinstance(payload, dict):
        raise ValidationError(["Payload must be a JSON object"])

    source = payload.get("source")
    dataset = payload.get("dataset")
    observation = payload.get("observation")
    measurements = payload.get("measurements")
    raw_artifact = payload.get("raw_artifact")
    processing = payload.get("processing")
    provenance = payload.get("provenance")

    if not isinstance(source, dict):
        errors.append("source is required")
    else:
        if not source.get("source_id"):
            errors.append("source.source_id is required")
        if source.get("source_type") not in VALID_SOURCE_TYPES:
            errors.append("source.source_type is invalid")
        if not source.get("title"):
            errors.append("source.title is required")
        if source.get("source_type") == "SYNTHETIC_TEST" and source.get("is_synthetic") is not True:
            errors.append("SYNTHETIC_TEST sources must set is_synthetic=true")

    if not isinstance(dataset, dict):
        errors.append("dataset is required")
    else:
        if not dataset.get("dataset_id"):
            errors.append("dataset.dataset_id is required")
        if not dataset.get("dataset_name"):
            errors.append("dataset.dataset_name is required")
        if not dataset.get("schema_version"):
            errors.append("dataset.schema_version is required")

    if not isinstance(observation, dict):
        errors.append("observation is required")
    else:
        if not observation.get("observation_type"):
            errors.append("observation.observation_type is required")
        confidence = observation.get("confidence")
        if confidence is not None and confidence not in VALID_CONFIDENCE:
            errors.append("observation.confidence is invalid")

    if not isinstance(measurements, list) or not measurements:
        errors.append("measurements must be a non-empty list")
    else:
        for index, measurement in enumerate(measurements):
            if not isinstance(measurement, dict):
                errors.append(f"measurements[{index}] must be an object")
                continue
            if not measurement.get("metric_name"):
                errors.append(f"measurements[{index}].metric_name is required")
            if measurement.get("value") is None:
                errors.append(f"measurements[{index}].value is required")
            if not measurement.get("unit"):
                errors.append(f"measurements[{index}].unit is required")

    if not isinstance(raw_artifact, dict):
        errors.append("raw_artifact is required")
    else:
        if raw_artifact.get("content") is None:
            errors.append("raw_artifact.content is required")
        if not raw_artifact.get("ref"):
            errors.append("raw_artifact.ref is required")

    if not isinstance(processing, dict):
        errors.append("processing is required")
    else:
        stage = processing.get("pipeline_stage", "INGEST")
        if stage not in VALID_PIPELINE_STAGES:
            errors.append("processing.pipeline_stage is invalid")
        if not processing.get("actor"):
            errors.append("processing.actor is required")

    if not isinstance(provenance, dict):
        errors.append("provenance is required")
    else:
        if not provenance.get("derivation_note"):
            errors.append("provenance.derivation_note is required")

    if errors:
        raise ValidationError(errors)
