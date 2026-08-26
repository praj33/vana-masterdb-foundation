import hashlib
import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

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
    raw_source = payload.get("source_identity") or payload.get("capture_method") or "group3-synthetic"
    clean_slug = raw_source.upper().replace("_", "-").replace(" ", "-")
    source_id = clean_slug if clean_slug.startswith("SRC-") else f"SRC-{clean_slug}"

    mission_id = payload.get("mission_id") or "TC-Z03-F02"
    dataset_id = f"DS-{clean_slug}-{mission_id}"

    is_synth_source = 1 if (payload.get("is_synthetic") or payload.get("synthetic_state") in ("SYNTHETIC", "SIMULATED")) else 0
    if conn.is_postgres:
        is_synth_source = bool(is_synth_source)

    source_type = "EXTERNAL_API" if payload.get("capture_method") == "external_api" else ("SYNTHETIC_TEST" if is_synth_source else "FIELD_CAPTURE")

    conn.execute(
        """
        INSERT INTO source (
            source_id,
            source_type,
            title,
            publisher,
            retrieved_at,
            is_synthetic,
            notes
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (source_id) DO NOTHING
        """,
        (
            source_id,
            source_type,
            f"VANA Source {source_id}",
            "VANA Group 3",
            utc_now(),
            is_synth_source,
            f"Source identity record for {raw_source}.",
        ),
    )

    conn.execute(
        """
        INSERT INTO dataset (
            dataset_id,
            dataset_name,
            source_id,
            methodology,
            schema_version,
            created_at,
            status
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (dataset_id) DO NOTHING
        """,
        (
            dataset_id,
            f"{mission_id} {source_id} Observations",
            source_id,
            f"Group 3 V{payload.get('contract_version', '2.2')} consumer observation contract",
            payload.get("schema_version", "2.2"),
            utc_now(),
            "REGISTERED",
        ),
    )

    return source_id, dataset_id


def _insert_geo(conn, observation_id: str, latitude, longitude, altitude_m=None):
    if latitude is None or longitude is None:
        return None

    geo_id = deterministic_id(
        "GEO",
        observation_id,
        str(latitude),
        str(longitude),
    )

    if conn.is_postgres:
        conn.execute(
            """
            INSERT INTO geo_location (
                geo_id,
                scope,
                place_name,
                geom,
                altitude_m,
                crs,
                notes
            )
            VALUES (?, ?, ?, ST_SetSRID(ST_MakePoint(?, ?), 4326), ?, ?, ?)
            ON CONFLICT (geo_id) DO NOTHING
            """,
            (
                geo_id,
                "POINT",
                "Group 3 observation location",
                longitude,
                latitude,
                altitude_m,
                "EPSG:4326",
                None,
            ),
        )
    else:
        conn.execute(
            """
            INSERT INTO geo_location (
                geo_id,
                scope,
                place_name,
                lat,
                lon,
                altitude_m,
                crs,
                notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (geo_id) DO NOTHING
            """,
            (
                geo_id,
                "POINT",
                "Group 3 observation location",
                latitude,
                longitude,
                altitude_m,
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
    meas_obj = observation.get("measurement")
    if isinstance(meas_obj, dict):
        value = meas_obj.get("value")
        unit = meas_obj.get("unit") or observation.get("unit")
    else:
        value = meas_obj
        unit = observation.get("unit")

    if value is None and not observation.get("parameter"):
        return None

    metric_name = observation.get("parameter") or observation.get("observation_type") or "observation_value"
    measurement_id = deterministic_id(
        "MEAS",
        observation_id,
        metric_name,
    )

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
        ON CONFLICT (measurement_id) DO NOTHING
        """,
        (
            measurement_id,
            observation_id,
            metric_name,
            "NUMERIC" if is_numeric else "TEXT",
            value if is_numeric else None,
            None if is_numeric else (str(value) if value is not None else None),
            unit,
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
        fingerprint = request_fingerprint(payload)
        key = idempotency_key or payload.get("idempotency_key")

        if key:
            existing = conn.execute(
                """
                SELECT observation_id, request_fingerprint, canonical_record_id
                FROM idempotency_record
                WHERE idempotency_key = ?
                """,
                (key,),
            ).fetchone()

            if existing:
                if existing[1] != fingerprint:
                    conn.rollback()
                    return {
                        "status": "IDEMPOTENCY_CONFLICT",
                        "observation_id": existing[0],
                        "canonical_record_id": None,
                        "http_status": 409,
                    }

                conn.commit()
                return {
                    "status": "IDEMPOTENT_REPLAY",
                    "observation_id": existing[0],
                    "canonical_record_id": existing[2],
                    "http_status": 200,
                }

        observation_id = payload["observation_id"]

        existing_observation = conn.execute(
            """
            SELECT observation_id, canonical_record_id
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
                "canonical_record_id": existing_observation[1],
                "http_status": 409,
            }

        source_id, dataset_id = ensure_source_and_dataset(conn, payload)

        location_obj = payload.get("location") if isinstance(payload.get("location"), dict) else {}
        latitude = location_obj.get("latitude") if "latitude" in location_obj else payload.get("latitude")
        longitude = location_obj.get("longitude") if "longitude" in location_obj else payload.get("longitude")
        altitude_m = location_obj.get("altitude_m") or payload.get("altitude_m") or payload.get("elevation")
        gnss_status = location_obj.get("gnss_status") or payload.get("gnss_status")
        position_accuracy_m = location_obj.get("position_accuracy_m") or payload.get("position_accuracy_m")

        geo_id = _insert_geo(
            conn,
            observation_id,
            latitude,
            longitude,
            altitude_m=altitude_m,
        )

        raw_capture = payload.get("capture_method") or payload.get("observation_type")
        capture_method = raw_capture if raw_capture in ('aerial', 'ground', 'sensor', 'site_evidence', 'external_api') else None

        observation_type = payload.get("parameter") or payload.get("observation_type") or "OBSERVATION"

        quality_status = payload.get("quality_state") or payload.get("quality_status") or "CAPTURED"

        # V2.2 synthetic_state & is_synthetic mapping
        synthetic_state = payload.get("synthetic_state")
        is_synth = payload.get("is_synthetic")

        if is_synth is None and synthetic_state:
            if synthetic_state in ("SYNTHETIC", "CONTROLLED", "SIMULATED"):
                is_synth = True
            elif synthetic_state == "PHYSICAL":
                is_synth = False
            else:
                is_synth = False
        elif is_synth is None:
            is_synth = False

        if not synthetic_state:
            synthetic_state = "SYNTHETIC" if is_synth else "UNKNOWN"

        is_synth_db = (1 if is_synth else 0) if not conn.is_postgres else bool(is_synth)
        observed_timestamp = payload.get("observation_timestamp") or payload.get("timestamp")

        canonical_record_id = f"CR-{uuid4()}"
        contract_version = payload.get("contract_version", "2.2")
        provenance_reference = payload.get("provenance_reference")

        conn.execute(
            """
            INSERT INTO observation (
                observation_id,
                canonical_record_id,
                dataset_id,
                geo_id,
                observed_at,
                capture_method,
                species,
                observation_type,
                quality_status,
                confidence,
                is_synthetic,
                synthetic_state,
                conflict_flag,
                conflict_notes,
                provenance_reference,
                contract_version,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                observation_id,
                canonical_record_id,
                dataset_id,
                geo_id,
                observed_timestamp,
                capture_method,
                None,
                observation_type,
                quality_status,
                None,
                is_synth_db,
                synthetic_state,
                0 if not conn.is_postgres else False,
                None,
                provenance_reference,
                contract_version,
                utc_now(),
            ),
        )

        accuracy_val = payload.get("accuracy")
        accuracy_num = float(accuracy_val) if isinstance(accuracy_val, (int, float)) else None
        accuracy_unit = payload.get("unit") if accuracy_num is not None else None

        cal_status = payload.get("calibration_state") or payload.get("calibration_status")
        if cal_status in ("NOT VERIFIED", "NOT_VERIFIED"):
            cal_status = "NOT_VERIFIED"

        accuracy_status = "NOT_VERIFIED" if cal_status == "NOT_VERIFIED" else ("SPECIFIED" if accuracy_num is not None else None)

        conn.execute(
            """
            INSERT INTO field_observation_meta (
                observation_id,
                device_id,
                operator,
                mission_id,
                accuracy,
                accuracy_unit,
                accuracy_status,
                calibration_status,
                gnss_status,
                position_accuracy_m,
                processing_status,
                notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (observation_id) DO NOTHING
            """,
            (
                observation_id,
                payload["device_id"],
                payload.get("provenance", {}).get("operator"),
                payload.get("provenance", {}).get("mission_id"),
                accuracy_num,
                accuracy_unit,
                accuracy_status,
                cal_status,
                gnss_status,
                position_accuracy_m,
                payload["processing_status"],
                None,
            ),
        )

        measurement_id = _insert_measurement(
            conn,
            observation_id,
            payload,
        )

        raw_art_path = payload.get("raw_artifact")
        raw_art_integrity = payload.get("raw_artifact_integrity") or {}

        if not raw_art_path and "raw_artifact_reference" in payload:
            ref = payload["raw_artifact_reference"] or {}
            if isinstance(ref, dict):
                raw_art_path = ref.get("path")
                if not raw_art_integrity:
                    raw_art_integrity = {
                        "checksum_sha256": ref.get("checksum_sha256"),
                        "hash_algorithm": "sha256" if ref.get("checksum_sha256") else None,
                        "artifact_type": ref.get("artifact_type", "other"),
                    }

        art_type = raw_art_integrity.get("artifact_type") or "other"
        checksum = raw_art_integrity.get("checksum_sha256")
        hash_algo = raw_art_integrity.get("hash_algorithm") or ("sha256" if checksum else None)

        artifact_id = deterministic_id(
            "ART",
            observation_id,
            art_type,
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
            ON CONFLICT (artifact_id) DO NOTHING
            """,
            (
                artifact_id,
                observation_id,
                art_type,
                raw_art_path or "UNSPECIFIED",
                checksum,
                hash_algo,
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
            ON CONFLICT (run_id) DO NOTHING
            """,
            (
                run_id,
                source_id,
                dataset_id,
                "GROUP3_INGESTION",
                "DONE",
                raw_art_path or "UNSPECIFIED",
                observation_id,
                None,
                observed_timestamp,
                utc_now(),
                payload.get("provenance", {}).get("operator", "GROUP3_API"),
            ),
        )

        provenance_id = deterministic_id(
            "PROV",
            measurement_id or artifact_id,
            source_id,
            run_id,
        )

        prov_dict = payload.get("provenance") if isinstance(payload.get("provenance"), dict) else {}
        derivation_note = prov_dict.get("derivation_note") or f"Group 3 V{contract_version} observation ingested through consumer-facing API."

        conn.execute(
            """
            INSERT INTO provenance (
                provenance_id,
                measurement_id,
                raw_artifact_id,
                source_id,
                run_id,
                derivation_note,
                recorded_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (provenance_id) DO NOTHING
            """,
            (
                provenance_id,
                measurement_id,
                artifact_id,
                source_id,
                run_id,
                derivation_note,
                utc_now(),
            ),
        )

        if key:
            conn.execute(
                """
                INSERT INTO idempotency_record (
                    idempotency_key,
                    observation_id,
                    canonical_record_id,
                    request_fingerprint,
                    fingerprint_algorithm,
                    first_response_status,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (idempotency_key) DO NOTHING
                """,
                (
                    key,
                    observation_id,
                    canonical_record_id,
                    fingerprint,
                    "sha256",
                    "CREATED",
                    utc_now(),
                ),
            )

        conn.commit()

        return {
            "status": "ACCEPTED",
            "observation_id": observation_id,
            "canonical_record_id": canonical_record_id,
            "http_status": 201,
            "run_id": run_id,
        }

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


def retrieve_observation(observation_id: str):
    conn = get_connection()

    try:
        if conn.is_postgres:
            query = """
                SELECT
                    o.observation_id,
                    o.canonical_record_id,
                    o.dataset_id,
                    o.geo_id,
                    o.observed_at,
                    o.capture_method,
                    o.species,
                    o.observation_type,
                    o.quality_status,
                    o.confidence,
                    o.is_synthetic,
                    o.synthetic_state,
                    g.place_name,
                    ST_Y(g.geom) AS lat,
                    ST_X(g.geom) AS lon,
                    g.altitude_m,
                    g.crs,
                    o.provenance_reference,
                    o.contract_version,
                    d.schema_version
                FROM observation o
                LEFT JOIN geo_location g
                    ON g.geo_id = o.geo_id
                LEFT JOIN dataset d
                    ON d.dataset_id = o.dataset_id
                WHERE o.observation_id = ?
            """
        else:
            query = """
                SELECT
                    o.observation_id,
                    o.canonical_record_id,
                    o.dataset_id,
                    o.geo_id,
                    o.observed_at,
                    o.capture_method,
                    o.species,
                    o.observation_type,
                    o.quality_status,
                    o.confidence,
                    o.is_synthetic,
                    o.synthetic_state,
                    g.place_name,
                    g.lat,
                    g.lon,
                    g.altitude_m,
                    g.crs,
                    o.provenance_reference,
                    o.contract_version,
                    d.schema_version
                FROM observation o
                LEFT JOIN geo_location g
                    ON g.geo_id = o.geo_id
                LEFT JOIN dataset d
                    ON d.dataset_id = o.dataset_id
                WHERE o.observation_id = ?
            """

        observation = conn.execute(query, (observation_id,)).fetchone()

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
                accuracy_status,
                calibration_status,
                gnss_status,
                position_accuracy_m,
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

        lat = float(observation[13]) if observation[13] is not None else None
        lon = float(observation[14]) if observation[14] is not None else None
        alt = float(observation[15]) if observation[15] is not None else None

        first_art = artifacts[0] if artifacts else None

        return {
            "observation_id": observation[0],
            "canonical_record_id": observation[1],
            "dataset_id": observation[2],
            "geo_id": observation[3],
            "observed_at": str(observation[4]) if observation[4] is not None else None,
            "observation_timestamp": str(observation[4]) if observation[4] is not None else None,
            "timestamp": str(observation[4]) if observation[4] is not None else None,
            "contract_version": observation[18] if observation[18] is not None else "2.2",
            "schema_version": observation[19] if observation[19] is not None else "2.2",
            "provenance_reference": observation[17],
            "capture_method": observation[5],
            "device_id": field_meta[0] if field_meta else None,
            "species": observation[6],
            "observation_type": observation[7],
            "quality_status": observation[8],
            "quality_state": observation[8],
            "data_state": observation[8],
            "confidence": observation[9],
            "is_synthetic": bool(observation[10]),
            "synthetic_state": observation[11],
            "location": {
                "latitude": lat,
                "longitude": lon,
                "altitude_m": alt,
                "gnss_status": field_meta[7] if field_meta else None,
                "position_accuracy_m": float(field_meta[8]) if (field_meta and field_meta[8] is not None) else None,
            },
            "latitude": lat,
            "longitude": lon,
            "altitude_m": alt,
            "gnss_status": field_meta[7] if field_meta else None,
            "position_accuracy_m": float(field_meta[8]) if (field_meta and field_meta[8] is not None) else None,
            "calibration_status": field_meta[6] if field_meta else None,
            "calibration_state": field_meta[6] if field_meta else None,
            "raw_artifact": first_art[2] if first_art else None,
            "raw_artifact_integrity": {
                "checksum_sha256": first_art[3] if first_art else None,
                "hash_algorithm": first_art[4] if first_art else None,
                "artifact_type": first_art[1] if first_art else "other",
            } if first_art else None,
            "raw_artifact_reference": {
                "path": first_art[2] if first_art else None,
                "checksum_sha256": first_art[3] if first_art else None,
                "artifact_type": first_art[1] if first_art else "other",
            } if first_art else None,
            "geo_location": (
                {
                    "place_name": observation[12],
                    "latitude": lat,
                    "longitude": lon,
                    "altitude_m": alt,
                    "crs": observation[16],
                }
                if observation[12] is not None or lat is not None
                else None
            ),
            "field_observation_meta": (
                {
                    "device_id": field_meta[0],
                    "operator": field_meta[1],
                    "mission_id": field_meta[2],
                    "accuracy": field_meta[3],
                    "accuracy_unit": field_meta[4],
                    "accuracy_status": field_meta[5],
                    "calibration_status": field_meta[6],
                    "gnss_status": field_meta[7],
                    "position_accuracy_m": float(field_meta[8]) if field_meta[8] is not None else None,
                    "processing_status": field_meta[9],
                    "notes": field_meta[10],
                }
                if field_meta
                else None
            ),
            "measurements": [
                {
                    "measurement_id": row[0],
                    "metric_name": row[1],
                    "data_type": row[2],
                    "value": float(row[3]) if row[3] is not None else None,
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
                    "captured_at": str(row[5]) if row[5] is not None else None,
                }
                for row in artifacts
            ],
        }

    finally:
        conn.close()
