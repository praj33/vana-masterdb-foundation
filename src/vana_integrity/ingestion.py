"""Canonical observation ingestion in a single database transaction."""

from __future__ import annotations

import sqlite3
import uuid
from typing import Any

from vana_integrity.idempotency import (
    IdempotencyConflictError,
    check_idempotency,
    compute_request_fingerprint,
    record_idempotency,
)
from vana_integrity.identity import resolve_observation_id
from vana_integrity.raw_artifact import extract_raw_artifact, format_input_ref
from vana_integrity.validation import ValidationError, validate_ingestion_payload


class ObservationExistsError(Exception):
    """Raised when the same observation id is ingested again without idempotency replay."""

    def __init__(self, observation_id: str) -> None:
        self.observation_id = observation_id
        super().__init__(f"Observation '{observation_id}' already exists")


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def ingest_observation(
    conn: sqlite3.Connection,
    payload: dict[str, Any],
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """Validate and persist a full provenance chain within one transaction."""
    validate_ingestion_payload(payload)
    request_fingerprint = compute_request_fingerprint(payload)

    conn.execute("BEGIN IMMEDIATE")
    try:
        prior = check_idempotency(conn, idempotency_key, request_fingerprint)
        if prior is not None:
            conn.commit()
            return {
                "observation_id": prior["observation_id"],
                "logical_identity": prior.get("logical_identity") or prior["observation_id"],
                "http_status": 200,
                "idempotent": True,
            }

        observation_id, logical_identity = resolve_observation_id(payload)
        existing = conn.execute(
            "SELECT observation_id FROM observation WHERE observation_id = ?",
            (observation_id,),
        ).fetchone()
        if existing is not None:
            record_idempotency(
                conn,
                idempotency_key,
                observation_id,
                request_fingerprint,
                200,
            )
            conn.commit()
            return {
                "observation_id": observation_id,
                "logical_identity": logical_identity,
                "http_status": 200,
                "idempotent": True,
                "duplicate_observation": True,
            }

        source = payload["source"]
        dataset = payload["dataset"]
        observation = payload["observation"]
        measurements = payload["measurements"]
        processing = payload["processing"]
        provenance = payload["provenance"]
        raw_content, raw_ref = extract_raw_artifact(payload)
        input_ref = format_input_ref(raw_content, raw_ref)

        conn.execute(
            """
            INSERT INTO source (
                source_id, source_type, title, publisher, url, citation,
                retrieved_at, is_synthetic, notes
            ) VALUES (?, ?, ?, ?, ?, ?, datetime('now'), ?, ?)
            ON CONFLICT(source_id) DO UPDATE SET
                source_type = excluded.source_type,
                title = excluded.title,
                is_synthetic = excluded.is_synthetic
            """,
            (
                source["source_id"],
                source["source_type"],
                source["title"],
                source.get("publisher"),
                source.get("url"),
                source.get("citation"),
                1 if source.get("is_synthetic") else 0,
                source.get("notes"),
            ),
        )

        conn.execute(
            """
            INSERT INTO dataset (
                dataset_id, dataset_name, source_id, methodology,
                schema_version, created_at, status
            ) VALUES (?, ?, ?, ?, ?, datetime('now'), 'REGISTERED')
            ON CONFLICT(dataset_id) DO UPDATE SET
                dataset_name = excluded.dataset_name,
                methodology = excluded.methodology
            """,
            (
                dataset["dataset_id"],
                dataset["dataset_name"],
                source["source_id"],
                dataset.get("methodology"),
                dataset["schema_version"],
            ),
        )

        conn.execute(
            """
            INSERT INTO observation (
                observation_id, dataset_id, geo_id, observation_date,
                species, observation_type, confidence, conflict_flag,
                conflict_notes, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, NULL, datetime('now'))
            """,
            (
                observation_id,
                dataset["dataset_id"],
                observation.get("geo_id"),
                observation.get("observation_date"),
                observation.get("species"),
                observation["observation_type"],
                observation.get("confidence"),
            ),
        )

        measurement_ids: list[str] = []
        for measurement in measurements:
            measurement_id = _new_id("MSR")
            conn.execute(
                """
                INSERT INTO measurement (
                    measurement_id, observation_id, metric_name, value, unit,
                    method, original_value_text, transform_applied, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                """,
                (
                    measurement_id,
                    observation_id,
                    measurement["metric_name"],
                    measurement["value"],
                    measurement["unit"],
                    measurement.get("method"),
                    measurement.get("original_value_text"),
                    measurement.get("transform_applied"),
                ),
            )
            measurement_ids.append(measurement_id)

        run_id = _new_id("RUN")
        conn.execute(
            """
            INSERT INTO processing_run (
                run_id, source_id, dataset_id, pipeline_stage, status,
                input_ref, output_ref, error_detail, started_at,
                finished_at, actor
            ) VALUES (?, ?, ?, ?, 'DONE', ?, ?, NULL, datetime('now'), datetime('now'), ?)
            """,
            (
                run_id,
                source["source_id"],
                dataset["dataset_id"],
                processing.get("pipeline_stage", "INGEST"),
                input_ref,
                observation_id,
                processing["actor"],
            ),
        )

        for measurement_id in measurement_ids:
            provenance_id = _new_id("PRV")
            conn.execute(
                """
                INSERT INTO provenance (
                    provenance_id, measurement_id, source_id, run_id,
                    derivation_note, recorded_at
                ) VALUES (?, ?, ?, ?, ?, datetime('now'))
                """,
                (
                    provenance_id,
                    measurement_id,
                    source["source_id"],
                    run_id,
                    provenance["derivation_note"],
                ),
            )

        record_idempotency(
            conn,
            idempotency_key,
            observation_id,
            request_fingerprint,
            201,
        )
        conn.commit()
        return {
            "observation_id": observation_id,
            "logical_identity": logical_identity,
            "http_status": 201,
            "idempotent": False,
            "run_id": run_id,
            "input_ref": input_ref,
        }
    except IdempotencyConflictError:
        conn.rollback()
        raise
    except Exception:
        conn.rollback()
        raise
