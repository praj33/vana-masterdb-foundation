import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from api.db import get_connection


def _fingerprint(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _record_id(payload: dict[str, Any]) -> str:
    record = payload.get("source_record_id") or ""
    dataset = payload["dataset"]["dataset_id"]
    geography = "|".join(
        [dataset, payload["geography_level"], payload["state"], payload.get("district") or "", record]
    )
    return "FC-" + hashlib.sha256(geography.encode("utf-8")).hexdigest()[:32]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def validate_official_record(payload: dict[str, Any]) -> list[str]:
    errors = []
    if payload.get("source", {}).get("source_type", "GOVERNMENT_DATASET") != "GOVERNMENT_DATASET":
        errors.append("source.source_type must be GOVERNMENT_DATASET")
    if not 1000 <= payload.get("assessment_year", 0) <= 9999:
        errors.append("assessment_year must be a four-digit year")
    level = payload.get("geography_level")
    if level not in ("STATE", "DISTRICT"):
        errors.append("geography_level must be STATE or DISTRICT")
    if not str(payload.get("state", "")).strip():
        errors.append("state is required")
    if level == "DISTRICT" and not str(payload.get("district", "")).strip():
        errors.append("district is required for DISTRICT records")
    if level == "STATE" and payload.get("district") is not None:
        errors.append("district must be null for STATE records")
    if not str(payload.get("provenance_reference", "")).strip():
        errors.append("provenance_reference is required")
    if payload.get("quality_status") not in ("UNVERIFIED", "EXTRACTED", "VALIDATED", "REJECTED"):
        errors.append("quality_status is invalid")
    for field in ("forest_cover_area", "very_dense_forest_area", "moderately_dense_forest_area", "open_forest_area", "mangrove_area"):
        value = payload.get(field)
        if value is not None and value < 0:
            errors.append(f"{field} must be non-negative")
    percentage = payload.get("forest_cover_percentage")
    if percentage is not None and not 0 <= percentage <= 100:
        errors.append("forest_cover_percentage must be between 0 and 100")
    return errors


def persist_official_forest_cover(payload: dict[str, Any], idempotency_key: str | None = None) -> dict[str, Any]:
    conn = get_connection()
    try:
        key = idempotency_key or payload.get("idempotency_key")
        body = dict(payload)
        body.pop("idempotency_key", None)
        fingerprint = _fingerprint(body)
        record_id = _record_id(payload)

        if key:
            existing_key = conn.execute(
                "SELECT record_id, request_fingerprint FROM official_forest_cover_record WHERE idempotency_key = ?",
                (key,),
            ).fetchone()
            if existing_key:
                if existing_key[1] != fingerprint:
                    conn.rollback()
                    return {"status": "CONFLICT", "record_id": existing_key[0], "http_status": 409}
                conn.commit()
                return {"status": "REPLAY", "record_id": existing_key[0], "http_status": 200}

        existing = conn.execute(
            "SELECT request_fingerprint FROM official_forest_cover_record WHERE record_id = ?",
            (record_id,),
        ).fetchone()
        if existing:
            if existing[0] != fingerprint:
                conn.rollback()
                return {"status": "CONFLICT", "record_id": record_id, "http_status": 409}
            conn.commit()
            return {"status": "REPLAY", "record_id": record_id, "http_status": 200}

        source = payload["source"]
        dataset = payload["dataset"]
        existing_source = conn.execute(
            "SELECT source_type, title, publisher, url, retrieved_at FROM source WHERE source_id = ?",
            (source["source_id"],),
        ).fetchone()
        if existing_source and existing_source != ("GOVERNMENT_DATASET", source["source_name"], source["publisher"], source["source_url"], source["retrieved_at"]):
            conn.rollback()
            return {"status": "CONFLICT", "record_id": record_id, "http_status": 409}
        conn.execute(
            """
            INSERT INTO source (source_id, source_type, title, publisher, url, citation, retrieved_at, is_synthetic, notes)
            VALUES (?, 'GOVERNMENT_DATASET', ?, ?, ?, ?, ?, 0, ?)
            ON CONFLICT (source_id) DO NOTHING
            """,
            (source["source_id"], source["source_name"], source["publisher"], source["source_url"], source.get("citation"), source["retrieved_at"], "Official government dataset"),
        )
        existing_dataset = conn.execute(
            "SELECT dataset_name, source_id, methodology FROM dataset WHERE dataset_id = ?",
            (dataset["dataset_id"],),
        ).fetchone()
        if existing_dataset and existing_dataset != (dataset["dataset_name"], source["source_id"], dataset.get("methodology")):
            conn.rollback()
            return {"status": "CONFLICT", "record_id": record_id, "http_status": 409}
        conn.execute(
            """
            INSERT INTO dataset (dataset_id, dataset_name, source_id, methodology, schema_version, created_at, status)
            VALUES (?, ?, ?, ?, '0.9.4', CURRENT_TIMESTAMP, 'REGISTERED')
            ON CONFLICT (dataset_id) DO NOTHING
            """,
            (dataset["dataset_id"], dataset["dataset_name"], source["source_id"], dataset.get("methodology")),
        )
        run_id = "RUN-" + hashlib.sha256((dataset["dataset_id"] + fingerprint).encode("utf-8")).hexdigest()[:32]
        conn.execute(
            """
            INSERT INTO processing_run (run_id, source_id, dataset_id, pipeline_stage, status, input_ref, output_ref, started_at, finished_at, actor)
            VALUES (?, ?, ?, 'OFFICIAL_DATASET_INGESTION', 'DONE', ?, ?, ?, ?, 'official-forest-cover-api')
            ON CONFLICT (run_id) DO NOTHING
            """,
            (run_id, source["source_id"], dataset["dataset_id"], source["source_url"], record_id, _utc_now(), _utc_now()),
        )
        conn.execute(
            """
            INSERT INTO official_forest_cover_record (
                record_id, dataset_id, source_record_id, assessment_year, geography_level, state, district,
                boundary_reference, forest_cover_area, forest_cover_percentage, very_dense_forest_area,
                moderately_dense_forest_area, open_forest_area, mangrove_area, unit, methodology,
                quality_status, provenance_reference, request_fingerprint, idempotency_key, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (record_id, dataset["dataset_id"], payload.get("source_record_id"), payload["assessment_year"], payload["geography_level"], payload["state"], payload.get("district"), payload.get("boundary_reference"), payload.get("forest_cover_area"), payload.get("forest_cover_percentage"), payload.get("very_dense_forest_area"), payload.get("moderately_dense_forest_area"), payload.get("open_forest_area"), payload.get("mangrove_area"), payload.get("unit"), payload.get("methodology"), payload.get("quality_status", "UNVERIFIED"), payload["provenance_reference"], fingerprint, key),
        )
        conn.commit()
        return {"status": "ACCEPTED", "record_id": record_id, "http_status": 201}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def retrieve_official_forest_cover(record_id: str):
    conn = get_connection()
    try:
        row = conn.execute(
            """
            SELECT r.record_id, r.dataset_id, d.dataset_name, s.source_id, s.title, s.publisher, s.url,
                   s.retrieved_at, r.source_record_id, r.assessment_year, r.geography_level, r.state,
                   r.district, r.boundary_reference, r.forest_cover_area, r.forest_cover_percentage,
                   r.very_dense_forest_area, r.moderately_dense_forest_area, r.open_forest_area,
                   r.mangrove_area, r.unit, r.methodology, r.quality_status, r.provenance_reference
            FROM official_forest_cover_record r
            JOIN dataset d ON d.dataset_id = r.dataset_id
            JOIN source s ON s.source_id = d.source_id
            WHERE r.record_id = ?
            """,
            (record_id,),
        ).fetchone()
        if not row:
            return None
        return _row_to_dict(row)
    finally:
        conn.close()


def list_official_forest_cover(dataset_id: str):
    conn = get_connection()
    try:
        rows = conn.execute(
                 """
                 SELECT r.record_id, r.dataset_id, d.dataset_name, s.source_id, s.title, s.publisher, s.url,
                     s.retrieved_at, r.source_record_id, r.assessment_year, r.geography_level, r.state,
                     r.district, r.boundary_reference, r.forest_cover_area, r.forest_cover_percentage,
                     r.very_dense_forest_area, r.moderately_dense_forest_area, r.open_forest_area,
                     r.mangrove_area, r.unit, r.methodology, r.quality_status, r.provenance_reference
                 FROM official_forest_cover_record r
                 JOIN dataset d ON d.dataset_id = r.dataset_id
                 JOIN source s ON s.source_id = d.source_id
                 WHERE r.dataset_id = ? ORDER BY r.geography_level, r.state, r.district
                 """,
            (dataset_id,),
        ).fetchall()
        return [_row_to_dict(row) for row in rows]
    finally:
        conn.close()


def _row_to_dict(row):
    return {
        "record_id": row[0], "dataset_id": row[1], "dataset_name": row[2],
        "source": {"source_id": row[3], "source_name": row[4], "publisher": row[5], "source_url": row[6], "retrieved_at": row[7]},
        "source_record_id": row[8], "assessment_year": row[9], "geography_level": row[10],
        "state": row[11], "district": row[12], "boundary_reference": row[13],
        "forest_cover_area": row[14], "forest_cover_percentage": row[15],
        "very_dense_forest_area": row[16], "moderately_dense_forest_area": row[17],
        "open_forest_area": row[18], "mangrove_area": row[19], "unit": row[20],
        "methodology": row[21], "quality_status": row[22], "provenance_reference": row[23],
    }