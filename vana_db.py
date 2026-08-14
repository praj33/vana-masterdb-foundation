"""
vana_db.py — insert/retrieve functions against VANA schema v0.2.

Import this from seed.py or test scripts. Talks to whatever
VANA_DATABASE_URL points at; only the SQLite path is exercised in
this sandbox (see init_db.py docstring for why).
"""

import os
import sqlite3
import hashlib
from datetime import datetime, timezone

DB_URL = os.environ.get("VANA_DATABASE_URL", "sqlite:///vana.db")


def now():
    return datetime.now(timezone.utc).isoformat()


def get_conn():
    assert DB_URL.startswith("sqlite:///"), "Only sqlite path implemented in this sandbox; see init_db.py for the Postgres path."
    path = DB_URL.replace("sqlite:///", "", 1)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def deterministic_id(prefix, *parts):
    h = hashlib.sha256("|".join(parts).encode()).hexdigest()[:12]
    return f"{prefix}-{h}"


def insert_observation(conn, *, observation_id, dataset_id, geo_id, observed_at,
                        capture_method, species, observation_type, quality_status,
                        confidence, measurements, source_id, run_id, derivation_note,
                        field_meta=None, raw_artifact=None):
    """
    Idempotent insert: same observation_id submitted twice results in
    exactly one observation row and exactly one row per measurement
    (measurement_id is deterministic from observation_id+metric+method).
    Returns (created: bool) — False if the observation already existed.
    """
    cur = conn.cursor()

    exists = cur.execute(
        "SELECT 1 FROM observation WHERE observation_id = ?", (observation_id,)
    ).fetchone()
    if exists:
        return False

    cur.execute("""
        INSERT INTO observation (observation_id, dataset_id, geo_id, observed_at,
                                  capture_method, species, observation_type,
                                  quality_status, confidence, conflict_flag,
                                  conflict_notes, created_at)
        VALUES (?,?,?,?,?,?,?,?,?,0,NULL,?)
    """, (observation_id, dataset_id, geo_id, observed_at, capture_method, species,
          observation_type, quality_status, confidence, now()))

    if field_meta:
        cur.execute("""
            INSERT INTO field_observation_meta
            (observation_id, device_id, operator, mission_id, accuracy, accuracy_unit,
             calibration_status, processing_status, notes)
            VALUES (?,?,?,?,?,?,?,?,?)
        """, (observation_id, field_meta.get("device_id"), field_meta.get("operator"),
              field_meta.get("mission_id"), field_meta.get("accuracy"),
              field_meta.get("accuracy_unit"), field_meta.get("calibration_status"),
              field_meta.get("processing_status"), field_meta.get("notes")))

    if raw_artifact:
        artifact_id = deterministic_id("ART", observation_id, raw_artifact["artifact_type"])
        cur.execute("""
            INSERT INTO raw_artifact (artifact_id, observation_id, artifact_type,
                                       storage_ref, content_hash, hash_algorithm,
                                       captured_at, notes)
            VALUES (?,?,?,?,?,?,?,?)
        """, (artifact_id, observation_id, raw_artifact["artifact_type"],
              raw_artifact["storage_ref"], raw_artifact.get("content_hash"),
              raw_artifact.get("hash_algorithm"), raw_artifact.get("captured_at"),
              raw_artifact.get("notes")))

    for m in measurements:
        measurement_id = deterministic_id("MEAS", observation_id, m["metric_name"], m.get("method", ""))
        cur.execute("""
            INSERT INTO measurement (measurement_id, observation_id, metric_name, value,
                                      unit, method, original_value_text, transform_applied, created_at)
            VALUES (?,?,?,?,?,?,?,?,?)
        """, (measurement_id, observation_id, m["metric_name"], m["value"], m["unit"],
              m.get("method"), m.get("original_value_text"), m.get("transform_applied"), now()))

        provenance_id = deterministic_id("PROV", measurement_id, source_id)
        cur.execute("""
            INSERT INTO provenance (provenance_id, measurement_id, source_id, run_id,
                                     derivation_note, recorded_at)
            VALUES (?,?,?,?,?,?)
        """, (provenance_id, measurement_id, source_id, run_id, derivation_note, now()))

    conn.commit()
    return True


def retrieve_observation(conn, observation_id):
    cur = conn.cursor()
    obs = cur.execute("""
        SELECT o.observation_id, o.dataset_id, o.observed_at, o.capture_method,
               o.species, o.observation_type, o.quality_status, o.confidence,
               g.place_name, g.lat, g.lon
        FROM observation o
        LEFT JOIN geography g ON g.geo_id = o.geo_id
        WHERE o.observation_id = ?
    """, (observation_id,)).fetchone()
    if not obs:
        return None

    measurements = cur.execute("""
        SELECT m.metric_name, m.value, m.unit, m.method, p.derivation_note, s.source_id, s.title
        FROM measurement m
        JOIN provenance p ON p.measurement_id = m.measurement_id
        JOIN source s ON s.source_id = p.source_id
        WHERE m.observation_id = ?
    """, (observation_id,)).fetchall()

    field_meta = cur.execute(
        "SELECT device_id, operator, mission_id, accuracy, accuracy_unit, calibration_status "
        "FROM field_observation_meta WHERE observation_id = ?", (observation_id,)
    ).fetchone()

    artifacts = cur.execute(
        "SELECT artifact_id, artifact_type, storage_ref, content_hash FROM raw_artifact "
        "WHERE observation_id = ?", (observation_id,)
    ).fetchall()

    return {
        "observation_id": obs[0], "dataset_id": obs[1], "observed_at": obs[2],
        "capture_method": obs[3], "species": obs[4], "observation_type": obs[5],
        "quality_status": obs[6], "confidence": obs[7],
        "geography": {"place_name": obs[8], "lat": obs[9], "lon": obs[10]} if obs[8] else None,
        "measurements": [
            {"metric": r[0], "value": r[1], "unit": r[2], "method": r[3],
             "provenance": r[4], "source_id": r[5], "source_title": r[6]}
            for r in measurements
        ],
        "field_meta": {
            "device_id": field_meta[0], "operator": field_meta[1], "mission_id": field_meta[2],
            "accuracy": field_meta[3], "accuracy_unit": field_meta[4],
            "calibration_status": field_meta[5],
        } if field_meta else None,
        "raw_artifacts": [
            {"artifact_id": a[0], "type": a[1], "storage_ref": a[2], "content_hash": a[3]}
            for a in artifacts
        ],
    }
