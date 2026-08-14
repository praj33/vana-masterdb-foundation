import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from api.db import get_connection


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def request_fingerprint(payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def deterministic_id(prefix: str, *parts: str) -> str:
    canonical = "|".join(str(part) for part in parts)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]
    return f"{prefix}-{digest}"


def ensure_source_and_dataset(
    conn,
    payload: dict[str, Any],
) -> tuple[str, str]:
    source_id = "SRC-GROUP3-SYNTHETIC"
    dataset_id = "DS-GROUP3-TC-Z03-F02"

    conn.execute(
        """
        INSERT OR IGNORE INTO source (
            source_id,
            source_type,
            title,
            publisher,
            retrieved_at,
            is_synthetic,
            notes
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            source_id,
            "SYNTHETIC_TEST",
            "Group 3 Synthetic Mission Package",
            "VANA Group 3",
            utc_now(),
            1,
            "Synthetic fixture used for API integration evidence.",
        ),
    )

    conn.execute(
        """
        INSERT OR IGNORE INTO dataset (
            dataset_id,
            dataset_name,
            source_id,
            methodology,
            schema_version,
            created_at,
            status
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            dataset_id,
            "TC-Z03-F02 Group 3 Observations",
            source_id,
            "Group 3 V1.0 consumer observation contract",
            "0.4",
            utc_now(),
            "REGISTERED",
        ),
    )

    return source_id, dataset_id


def _insert_geo(conn, observation_id: str, latitude, longitude):
    if latitude is None or longitude is None:
        return None

    geo_id = deterministic_id(
        "GEO",
        observation_id,
        str(latitude),
        str(longitude),
    )

    conn.execute(
        """
        INSERT OR IGNORE INTO geo_location (
            geo_id,
            scope,
            place_name,
            lat,
            lon,
            crs,
            notes
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            geo_id,
            "POINT",
            "Group 3 observation location",
            latitude,
            longitude,
            "EPSG:4326",
            None,
        ),
    )

    return geo_id


def _insert_measurement(
    conn,
    observation_id: str,
    observation: dict[str, Any],
):
    measurement_id = deterministic_id(
        "MEAS",
        observation_id,
        observation["parameter"]
        if observation.get("parameter")
        else observation["observation_type"],
    )

    value = observation.get("measurement")
    is_numeric = isinstance(value, (int, float)) and not isinstance(value, bool)

    conn.execute(
        """
        INSERT INTO measurement (
            measurement_id,
            observation_id,
            metric_name,
            data_type,
            value,
            value_text,
            unit,
            method,
            original_value_text,
            transform_applied,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            measurement_id,
            observation_id,
            observation.get("parameter", observation["observation_type"]),
            "NUMERIC" if is_numeric else "TEXT",
            value if is_numeric else None,
            None if is_numeric else str(value),
            observation.get("unit"),
            observation.get("observation_type"),
            None,
            None,
            utc_now(),
        ),
    )

    return measurement_id


def persist_observation(
    payload: dict[str, Any],
    idempotency_key: str | None = None,
):
    conn = get_connection()

    try:
        conn.execute("BEGIN")

        fingerprint = request_fingerprint(payload)

        if idempotency_key:
            existing = conn.execute(
                """
                SELECT observation_id, request_fingerprint
                FROM idempotency_record
                WHERE idempotency_key = ?
                """,
                (idempotency_key,),
            ).fetchone()

            if existing:
                if existing[1] != fingerprint:
                    conn.rollback()
                    return {
                        "status": "IDEMPOTENCY_CONFLICT",
                        "observation_id": existing[0],
                        "http_status": 409,
                    }

                conn.commit()
                return {
                    "status": "IDEMPOTENT_REPLAY",
                    "observation_id": existing[0],
                    "http_status": 200,
                }

        observation_id = payload["observation_id"]

        existing_observation = conn.execute(
            """
            SELECT observation_id
            FROM observation
            WHERE observation_id = ?
            """,
            (observation_id,),
        ).fetchone()

        if existing_observation:
            conn.rollback()
            return {
                "status": "DUPLICATE",
                "observation_id": observation_id,
                "http_status": 409,
            }

        source_id, dataset_id = ensure_source_and_dataset(conn, payload)

        geo_id = _insert_geo(
            conn,
            observation_id,
            payload.get("latitude"),
            payload.get("longitude"),
        )

        conn.execute(
            """
            INSERT INTO observation (
                observation_id,
                dataset_id,
                geo_id,
                observed_at,
                capture_method,
                species,
                observation_type,
                quality_status,
                confidence,
                conflict_flag,
                conflict_notes,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                observation_id,
                dataset_id,
                geo_id,
                payload["timestamp"],
                payload.get("sensor_id"),
                None,
                payload["observation_type"],
                payload["quality_status"],
                None,
                0,
                None,
                utc_now(),
            ),
        )

        conn.execute(
            """
            INSERT INTO field_observation_meta (
                observation_id,
                device_id,
                operator,
                mission_id,
                accuracy,
                accuracy_unit,
                calibration_status,
                processing_status,
                notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                observation_id,
                payload["device_id"],
                payload.get("provenance", {}).get("operator"),
                payload.get("provenance", {}).get("mission_id"),
                None,
                payload.get("accuracy"),
                payload["calibration_status"],
                payload["processing_status"],
                None,
            ),
        )

        measurement_id = _insert_measurement(
            conn,
            observation_id,
            payload,
        )

        raw = payload["raw_artifact_reference"]

        artifact_id = deterministic_id(
            "ART",
            observation_id,
            raw["artifact_type"],
        )

        conn.execute(
            """
            INSERT INTO raw_artifact (
                artifact_id,
                observation_id,
                artifact_type,
                storage_ref,
                content_hash,
                hash_algorithm,
                captured_at,
                notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                artifact_id,
                observation_id,
                raw["artifact_type"],
                raw["path"],
                raw.get("checksum_sha256"),
                "sha256" if raw.get("checksum_sha256") else None,
                payload.get("provenance", {}).get("captured_at"),
                None,
            ),
        )

        run_id = deterministic_id(
            "RUN",
            observation_id,
            payload["processing_status"],
        )

        conn.execute(
            """
            INSERT INTO processing_run (
                run_id,
                source_id,
                dataset_id,
                pipeline_stage,
                status,
                input_ref,
                output_ref,
                error_detail,
                started_at,
                finished_at,
                actor
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                source_id,
                dataset_id,
                "GROUP3_INGESTION",
                "DONE",
                raw["path"],
                observation_id,
                None,
                payload["timestamp"],
                utc_now(),
                payload.get("provenance", {}).get("operator", "GROUP3_API"),
            ),
        )

        provenance_id = deterministic_id(
            "PROV",
            measurement_id,
            source_id,
            run_id,
        )

        conn.execute(
            """
            INSERT INTO provenance (
                provenance_id,
                measurement_id,
                source_id,
                run_id,
                derivation_note,
                recorded_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                provenance_id,
                measurement_id,
                source_id,
                run_id,
                "Group 3 V1.0 observation ingested through consumer-facing API.",
                utc_now(),
            ),
        )

        if idempotency_key:
            conn.execute(
                """
                INSERT INTO idempotency_record (
                    idempotency_key,
                    observation_id,
                    request_fingerprint,
                    fingerprint_algorithm,
                    first_response_status,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    idempotency_key,
                    observation_id,
                    fingerprint,
                    "sha256",
                    "201",
                    utc_now(),
                ),
            )

        conn.commit()

        return {
            "status": "ACCEPTED",
            "observation_id": observation_id,
            "http_status": 201,
            "run_id": run_id,
        }

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()
# ---------------------------------------------------------------------------
# Canonical retrieval
# ---------------------------------------------------------------------------

def retrieve_observation(observation_id: str):
    conn = get_connection()

    try:
        observation = conn.execute(
            """
            SELECT
                o.observation_id,
                o.dataset_id,
                o.geo_id,
                o.observed_at,
                o.capture_method,
                o.species,
                o.observation_type,
                o.quality_status,
                o.confidence,
                g.place_name,
                g.lat,
                g.lon,
                g.crs
            FROM observation o
            LEFT JOIN geo_location g
                ON g.geo_id = o.geo_id
            WHERE o.observation_id = ?
            """,
            (observation_id,),
        ).fetchone()

        if not observation:
            return None

        field_meta = conn.execute(
            """
            SELECT
                device_id,
                operator,
                mission_id,
                accuracy,
                accuracy_unit,
                calibration_status,
                processing_status,
                notes
            FROM field_observation_meta
            WHERE observation_id = ?
            """,
            (observation_id,),
        ).fetchone()

        measurements = conn.execute(
            """
            SELECT
                m.measurement_id,
                m.metric_name,
                m.data_type,
                m.value,
                m.value_text,
                m.unit,
                m.method,
                p.provenance_id,
                p.source_id,
                p.run_id,
                p.derivation_note
            FROM measurement m
            LEFT JOIN provenance p
                ON p.measurement_id = m.measurement_id
            WHERE m.observation_id = ?
            ORDER BY m.measurement_id
            """,
            (observation_id,),
        ).fetchall()

        artifacts = conn.execute(
            """
            SELECT
                artifact_id,
                artifact_type,
                storage_ref,
                content_hash,
                hash_algorithm,
                captured_at
            FROM raw_artifact
            WHERE observation_id = ?
            ORDER BY artifact_id
            """,
            (observation_id,),
        ).fetchall()

        return {
            "observation_id": observation[0],
            "dataset_id": observation[1],
            "geo_id": observation[2],
            "observed_at": observation[3],
            "capture_method": observation[4],
            "species": observation[5],
            "observation_type": observation[6],
            "quality_status": observation[7],
            "confidence": observation[8],
            "geo_location": (
                {
                    "place_name": observation[9],
                    "latitude": observation[10],
                    "longitude": observation[11],
                    "crs": observation[12],
                }
                if observation[9] is not None
                else None
            ),
            "field_observation_meta": (
                {
                    "device_id": field_meta[0],
                    "operator": field_meta[1],
                    "mission_id": field_meta[2],
                    "accuracy": field_meta[3],
                    "accuracy_unit": field_meta[4],
                    "calibration_status": field_meta[5],
                    "processing_status": field_meta[6],
                    "notes": field_meta[7],
                }
                if field_meta
                else None
            ),
            "measurements": [
                {
                    "measurement_id": row[0],
                    "metric_name": row[1],
                    "data_type": row[2],
                    "value": row[3],
                    "value_text": row[4],
                    "unit": row[5],
                    "method": row[6],
                    "provenance": {
                        "provenance_id": row[7],
                        "source_id": row[8],
                        "run_id": row[9],
                        "derivation_note": row[10],
                    }
                    if row[7]
                    else None,
                }
                for row in measurements
            ],
            "raw_artifacts": [
                {
                    "artifact_id": row[0],
                    "artifact_type": row[1],
                    "storage_ref": row[2],
                    "content_hash": row[3],
                    "hash_algorithm": row[4],
                    "captured_at": row[5],
                }
                for row in artifacts
            ],
        }

    finally:
        conn.close()
