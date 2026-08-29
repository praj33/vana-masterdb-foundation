"""Canonical observation ingestion in a single atomic database transaction."""

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
    """Validate and persist a full provenance chain within one atomic transaction."""
    validate_ingestion_payload(payload)
    request_fingerprint = compute_request_fingerprint(payload)

    conn.execute("BEGIN IMMEDIATE")
    try:
        prior = check_idempotency(conn, idempotency_key, request_fingerprint)
        if prior is not None:
            conn.commit()
            return {
                "observation_id": prior["observation_id"],
                "http_status": 200,
                "idempotent": True,
            }

        observation_id = resolve_observation_id(payload)
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
                first_response_status="200",
            )
            conn.commit()
            return {
                "observation_id": observation_id,
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
        raw_artifact_block = payload.get("raw_artifact") or {}
        raw_content, raw_ref = extract_raw_artifact(payload)
        input_ref = format_input_ref(raw_content, raw_ref)

        # 1. Source
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

        # 2. Dataset
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

        # 3. Geo Location (POINT)
        geo_block = payload.get("geo_location") or observation.get("geo_location") or {}
        geo_id = observation.get("geo_id") or geo_block.get("geo_id")
        if not geo_id and (geo_block or observation.get("place_name") or observation.get("lat") is not None):
            geo_id = f"GEO-{observation_id}"

        if geo_id:
            place_name = geo_block.get("place_name") or observation.get("place_name") or "Unspecified"
            lat = geo_block.get("lat") if geo_block.get("lat") is not None else observation.get("lat", 0.0)
            lon = geo_block.get("lon") if geo_block.get("lon") is not None else observation.get("lon", 0.0)
            scope = geo_block.get("scope", "POINT")
            crs = geo_block.get("crs", "EPSG:4326")
            conn.execute(
                """
                INSERT INTO geo_location (
                    geo_id, scope, place_name, lat, lon, crs, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(geo_id) DO NOTHING
                """,
                (geo_id, scope, place_name, float(lat), float(lon), crs, geo_block.get("notes")),
            )

        # 4. Observation
        observed_at = (
            observation.get("observed_at")
            or observation.get("observation_date")
            or datetime_now_iso()
        )
        conn.execute(
            """
            INSERT INTO observation (
                observation_id, dataset_id, geo_id, observed_at,
                capture_method, species, observation_type, quality_status,
                confidence, conflict_flag, conflict_notes, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'CAPTURED', ?, 0, NULL, datetime('now'))
            """,
            (
                observation_id,
                dataset["dataset_id"],
                geo_id,
                observed_at,
                observation.get("capture_method"),
                observation.get("species"),
                observation["observation_type"],
                observation.get("confidence"),
            ),
        )

        # 5. Field Observation Meta (optional)
        field_meta = payload.get("field_observation_meta") or payload.get("field_meta") or {}
        if field_meta:
            conn.execute(
                """
                INSERT INTO field_observation_meta (
                    observation_id, device_id, operator, mission_id,
                    accuracy, accuracy_unit, calibration_status, processing_status, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(observation_id) DO NOTHING
                """,
                (
                    observation_id,
                    field_meta.get("device_id"),
                    field_meta.get("operator"),
                    field_meta.get("mission_id"),
                    field_meta.get("accuracy"),
                    field_meta.get("accuracy_unit"),
                    field_meta.get("calibration_status"),
                    field_meta.get("processing_status"),
                    field_meta.get("notes"),
                ),
            )

        # 6. Measurements
        measurement_ids: list[str] = []
        for measurement in measurements:
            measurement_id = _new_id("MSR")
            data_type = measurement.get("data_type", "NUMERIC")
            val = measurement.get("value")
            val_text = measurement.get("value_text")
            if data_type in ("TEXT", "BOOLEAN") and val_text is None and val is not None:
                val_text = str(val)

            conn.execute(
                """
                INSERT INTO measurement (
                    measurement_id, observation_id, metric_name, data_type,
                    value, value_text, unit, method, original_value_text,
                    transform_applied, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                """,
                (
                    measurement_id,
                    observation_id,
                    measurement["metric_name"],
                    data_type,
                    val,
                    val_text,
                    measurement.get("unit"),
                    measurement.get("method"),
                    measurement.get("original_value_text"),
                    measurement.get("transform_applied"),
                ),
            )
            measurement_ids.append(measurement_id)

        # 7. Raw Artifact
        artifact_id = _new_id("ART")
        artifact_type = raw_artifact_block.get("artifact_type", "DOCUMENT")
        storage_ref = raw_ref or raw_artifact_block.get("storage_ref") or "fixtures/synthetic_observation_001.json"
        conn.execute(
            """
            INSERT INTO raw_artifact (
                artifact_id, observation_id, artifact_type, storage_ref,
                content_hash, hash_algorithm, captured_at, notes
            ) VALUES (?, ?, ?, ?, ?, 'sha256', datetime('now'), ?)
            """,
            (
                artifact_id,
                observation_id,
                artifact_type,
                storage_ref,
                input_ref,
                raw_artifact_block.get("notes"),
            ),
        )

        # 8. Processing Run
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

        # 9. Provenance
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

        # 10. Idempotency Record
        record_idempotency(
            conn,
            idempotency_key,
            observation_id,
            request_fingerprint,
            first_response_status="201",
        )
        conn.commit()

        return {
            "observation_id": observation_id,
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


def datetime_now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def retrieve_observation(conn: sqlite3.Connection, observation_id: str) -> dict[str, Any] | None:
    """Retrieve full canonical observation record with all relational components."""
    obs = conn.execute(
        """
        SELECT o.observation_id, o.dataset_id, o.geo_id, o.observed_at,
               o.capture_method, o.species, o.observation_type, o.quality_status,
               o.confidence, o.conflict_flag, o.conflict_notes, o.created_at,
               d.dataset_name, d.schema_version, d.source_id,
               s.source_type, s.title AS source_title, s.is_synthetic
        FROM observation o
        JOIN dataset d ON d.dataset_id = o.dataset_id
        JOIN source s ON s.source_id = d.source_id
        WHERE o.observation_id = ?
        """,
        (observation_id,),
    ).fetchone()

    if obs is None:
        return None

    geo = None
    if obs["geo_id"]:
        geo_row = conn.execute(
            """
            SELECT geo_id, scope, place_name, lat, lon, crs, notes
            FROM geo_location
            WHERE geo_id = ?
            """,
            (obs["geo_id"],),
        ).fetchone()
        if geo_row is not None:
            geo = dict(geo_row)

    field_meta = None
    fmeta_row = conn.execute(
        """
        SELECT observation_id, device_id, operator, mission_id, accuracy,
               accuracy_unit, calibration_status, processing_status, notes
        FROM field_observation_meta
        WHERE observation_id = ?
        """,
        (observation_id,),
    ).fetchone()
    if fmeta_row is not None:
        field_meta = dict(fmeta_row)

    measurements = [
        dict(row)
        for row in conn.execute(
            """
            SELECT measurement_id, metric_name, data_type, value, value_text,
                   unit, method, original_value_text, transform_applied, created_at
            FROM measurement
            WHERE observation_id = ?
            ORDER BY rowid
            """,
            (observation_id,),
        ).fetchall()
    ]

    raw_artifacts = [
        dict(row)
        for row in conn.execute(
            """
            SELECT artifact_id, artifact_type, storage_ref, content_hash,
                   hash_algorithm, captured_at, notes
            FROM raw_artifact
            WHERE observation_id = ?
            ORDER BY rowid
            """,
            (observation_id,),
        ).fetchall()
    ]

    provenance_rows = [
        dict(row)
        for row in conn.execute(
            """
            SELECT p.provenance_id, p.measurement_id, p.source_id, p.run_id,
                   p.derivation_note, p.recorded_at
            FROM provenance p
            JOIN measurement m ON m.measurement_id = p.measurement_id
            WHERE m.observation_id = ?
            ORDER BY p.rowid
            """,
            (observation_id,),
        ).fetchall()
    ]

    return {
        "observation_id": obs["observation_id"],
        "canonical_record_id": obs["observation_id"],
        "dataset": {
            "dataset_id": obs["dataset_id"],
            "dataset_name": obs["dataset_name"],
            "schema_version": obs["schema_version"],
            "source_id": obs["source_id"],
        },
        "source": {
            "source_id": obs["source_id"],
            "source_type": obs["source_type"],
            "title": obs["source_title"],
            "is_synthetic": bool(obs["is_synthetic"]),
        },
        "observation": {
            "observation_id": obs["observation_id"],
            "observed_at": obs["observed_at"],
            "capture_method": obs["capture_method"],
            "species": obs["species"],
            "observation_type": obs["observation_type"],
            "quality_status": obs["quality_status"],
            "confidence": obs["confidence"],
            "created_at": obs["created_at"],
        },
        "geo_location": geo,
        "field_observation_meta": field_meta,
        "measurements": measurements,
        "raw_artifacts": raw_artifacts,
        "provenance": provenance_rows,
    }


