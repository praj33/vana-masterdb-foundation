"""
vana_db.py — insert/retrieve functions against VANA schema v0.3.

Works against BOTH backends, selected by VANA_DATABASE_URL:
  sqlite:///path.db                          -> sqlite3 (stdlib)
  postgresql://user:pass@host:5432/vana      -> psycopg2 (must be installed)

Import this from seed.py or test scripts.
"""

import os
import sqlite3
import hashlib
from datetime import datetime, timezone

DB_URL = os.environ.get("VANA_DATABASE_URL", "sqlite:///vana.db")
IS_POSTGRES = DB_URL.startswith("postgresql://") or DB_URL.startswith("postgres://")


def now():
    return datetime.now(timezone.utc).isoformat()


class _CursorWrapper:
    """Translates sqlite-style '?' placeholders to psycopg2-style '%s'
    so the exact same query text works against both backends."""
    def __init__(self, raw_cursor, is_postgres):
        self._cur = raw_cursor
        self._pg = is_postgres

    def execute(self, sql, params=()):
        if self._pg:
            sql = sql.replace("?", "%s")
        return self._cur.execute(sql, params)

    def fetchone(self):
        return self._cur.fetchone()

    def fetchall(self):
        return self._cur.fetchall()


class _ConnWrapper:
    def __init__(self, raw_conn, is_postgres):
        self._conn = raw_conn
        self.is_postgres = is_postgres

    def cursor(self):
        return _CursorWrapper(self._conn.cursor(), self.is_postgres)

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()


def get_conn():
    if IS_POSTGRES:
        try:
            import psycopg2
        except ImportError:
            raise RuntimeError(
                "VANA_DATABASE_URL points at Postgres but psycopg2 is not "
                "installed. Run: pip install psycopg2-binary"
            )
        raw = psycopg2.connect(DB_URL)
        return _ConnWrapper(raw, True)
    else:
        assert DB_URL.startswith("sqlite:///"), f"Unrecognized VANA_DATABASE_URL: {DB_URL}"
        path = DB_URL.replace("sqlite:///", "", 1)
        raw = sqlite3.connect(path)
        raw.execute("PRAGMA foreign_keys = ON")
        return _ConnWrapper(raw, False)


def deterministic_id(prefix, *parts):
    h = hashlib.sha256("|".join(parts).encode()).hexdigest()[:12]
    return f"{prefix}-{h}"


def insert_observation(conn, *, observation_id, dataset_id, geo_id, observed_at,
                        capture_method, species, observation_type, quality_status,
                        confidence, measurements, source_id, run_id, derivation_note,
                        field_meta=None, raw_artifact=None, is_synthetic=False,
                        synthetic_state="UNKNOWN"):
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
                                  quality_status, confidence, is_synthetic, synthetic_state,
                                  conflict_flag, conflict_notes, created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,NULL,?)
    """, (observation_id, dataset_id, geo_id, observed_at, capture_method, species,
          observation_type, quality_status, confidence, is_synthetic, synthetic_state, False, now()))

    if field_meta:
        cur.execute("""
            INSERT INTO field_observation_meta
            (observation_id, device_id, operator, mission_id, accuracy, accuracy_unit,
             accuracy_status, calibration_status, gnss_status, position_accuracy_m,
             processing_status, notes)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """, (observation_id, field_meta.get("device_id"), field_meta.get("operator"),
              field_meta.get("mission_id"), field_meta.get("accuracy"),
              field_meta.get("accuracy_unit"), field_meta.get("accuracy_status"),
              field_meta.get("calibration_status"), field_meta.get("gnss_status"),
              field_meta.get("position_accuracy_m"),
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
        # v0.6 fix: this used to be silently dropped — an artifact with
        # no derived measurement got NO provenance row at all. Now it
        # gets one, attached via raw_artifact_id instead of measurement_id.
        artifact_provenance_id = deterministic_id("PROV-ART", artifact_id, source_id)
        cur.execute("""
            INSERT INTO provenance (provenance_id, measurement_id, raw_artifact_id,
                                     source_id, run_id, derivation_note, recorded_at)
            VALUES (?,?,?,?,?,?,?)
        """, (artifact_provenance_id, None, artifact_id, source_id, run_id,
              derivation_note, now()))

    for m in measurements:
        measurement_id = deterministic_id("MEAS", observation_id, m["metric_name"], m.get("method", ""))
        data_type = m.get("data_type", "NUMERIC")
        if data_type == "NUMERIC":
            assert m.get("value") is not None, f"NUMERIC measurement {m['metric_name']} requires 'value'"
        else:
            assert m.get("value_text") is not None, f"{data_type} measurement {m['metric_name']} requires 'value_text'"
        cur.execute("""
            INSERT INTO measurement (measurement_id, observation_id, metric_name, data_type,
                                      value, value_text, unit, method, original_value_text,
                                      transform_applied, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """, (measurement_id, observation_id, m["metric_name"], data_type,
              m.get("value"), m.get("value_text"), m.get("unit"),
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
               o.species, o.observation_type, o.quality_status, o.confidence, o.is_synthetic,
               o.synthetic_state,
               g.place_name, g.lat, g.lon, g.altitude_m
        FROM observation o
        LEFT JOIN geo_location g ON g.geo_id = o.geo_id
        WHERE o.observation_id = ?
    """, (observation_id,)).fetchone()
    if not obs:
        return None

    measurements = cur.execute("""
        SELECT m.metric_name, m.data_type, m.value, m.value_text, m.unit, m.method,
               p.derivation_note, s.source_id, s.title
        FROM measurement m
        JOIN provenance p ON p.measurement_id = m.measurement_id
        JOIN source s ON s.source_id = p.source_id
        WHERE m.observation_id = ?
    """, (observation_id,)).fetchall()

    field_meta = cur.execute(
        "SELECT device_id, operator, mission_id, accuracy, accuracy_unit, accuracy_status, "
        "calibration_status, gnss_status, position_accuracy_m "
        "FROM field_observation_meta WHERE observation_id = ?", (observation_id,)
    ).fetchone()

    artifacts = cur.execute("""
        SELECT a.artifact_id, a.artifact_type, a.storage_ref, a.content_hash,
               p.derivation_note, s.source_id
        FROM raw_artifact a
        LEFT JOIN provenance p ON p.raw_artifact_id = a.artifact_id
        LEFT JOIN source s ON s.source_id = p.source_id
        WHERE a.observation_id = ?
    """, (observation_id,)).fetchall()

    return {
        "observation_id": obs[0], "dataset_id": obs[1], "observed_at": obs[2],
        "capture_method": obs[3], "species": obs[4], "observation_type": obs[5],
        "quality_status": obs[6], "confidence": obs[7], "is_synthetic": bool(obs[8]),
        "synthetic_state": obs[9],
        "geo_location": {"place_name": obs[10], "lat": obs[11], "lon": obs[12], "altitude_m": obs[13]} if obs[10] else None,
        "measurements": [
            {"metric": r[0], "data_type": r[1], "value": r[2], "value_text": r[3],
             "unit": r[4], "method": r[5], "provenance": r[6], "source_id": r[7], "source_title": r[8]}
            for r in measurements
        ],
        "field_meta": {
            "device_id": field_meta[0], "operator": field_meta[1], "mission_id": field_meta[2],
            "accuracy": field_meta[3], "accuracy_unit": field_meta[4],
            "accuracy_status": field_meta[5], "calibration_status": field_meta[6],
            "gnss_status": field_meta[7], "position_accuracy_m": field_meta[8],
        } if field_meta else None,
        "raw_artifacts": [
            {"artifact_id": a[0], "type": a[1], "storage_ref": a[2], "content_hash": a[3],
             "provenance": a[4], "source_id": a[5]}
            for a in artifacts
        ],
    }
