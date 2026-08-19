#!/usr/bin/env python3
"""
test_roundtrip.py — EOD evidence capture for Kavy's Day-6 deliverable.

Run after init_db.py + seed.py:
    python3 init_db.py && python3 seed.py && python3 test_roundtrip.py

Proves, against schema v0.2:
  1. Retrieval of the seed (literature) record, with provenance.
  2. Insert of a Group-3-SHAPED field observation exercising the new
     fields (observed_at, capture_method, field_observation_meta,
     raw_artifact) — SYNTHETIC/TEST, explicitly labelled, not
     presented as a real Group 3 submission.
  3. Duplicate submission of that same observation_id: 0 -> 1 -> 1.
  4. Invalid record rejection (missing required field), error captured.
"""

import sqlite3
import json
from vana_db import get_conn, insert_observation, retrieve_observation, now

conn = get_conn()

# ------------------------------------------------------------------
# 1. Retrieve the seed record
# ------------------------------------------------------------------
seed_result = retrieve_observation(conn, "OBS-THANECREEK-AGB-2023-01")
print("[1] Seed record retrieval:")
print(json.dumps(seed_result, indent=2))
assert seed_result is not None
assert len(seed_result["measurements"]) == 2

# ------------------------------------------------------------------
# 2/3. Group-3-shaped SYNTHETIC/TEST field observation, inserted
#      three times to prove idempotency: 0 -> 1 -> 1 -> 1
# ------------------------------------------------------------------
cur = conn.cursor()

SYN_SOURCE_ID = "SRC-SYNTHETIC-GROUP3-FIXTURE-01"
cur.execute("SELECT 1 FROM source WHERE source_id=?", (SYN_SOURCE_ID,))
if not cur.fetchone():
    cur.execute("""
        INSERT INTO source (source_id, source_type, title, publisher, url, citation,
                             retrieved_at, is_synthetic, notes)
        VALUES (?,?,?,?,?,?,?,?,?)
    """, (SYN_SOURCE_ID, "SYNTHETIC_TEST", "Synthetic Group 3 field-observation fixture",
          None, None, None, now(), True, "SYNTHETIC/TEST — not a real field observation."))

SYN_RUN_ID = "RUN-2026-08-19-TEST-001"
cur.execute("SELECT 1 FROM processing_run WHERE run_id=?", (SYN_RUN_ID,))
if not cur.fetchone():
    cur.execute("""
        INSERT INTO processing_run (run_id, source_id, dataset_id, pipeline_stage, status,
                                     input_ref, output_ref, error_detail, started_at, finished_at, actor)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
    """, (SYN_RUN_ID, SYN_SOURCE_ID, None, "TEST_INGEST", "DONE",
          "synthetic fixture", "idempotency + field-schema proof", None, now(), now(),
          "Kavy (Day-6 build, test_roundtrip.py)"))

SYN_DATASET_ID = "DS-SYNTHETIC-GROUP3-FIXTURE-01"
cur.execute("SELECT 1 FROM dataset WHERE dataset_id=?", (SYN_DATASET_ID,))
if not cur.fetchone():
    cur.execute("""
        INSERT INTO dataset (dataset_id, dataset_name, source_id, methodology,
                              schema_version, created_at, status)
        VALUES (?,?,?,?,?,?,?)
    """, (SYN_DATASET_ID, "Synthetic Group 3 fixture dataset", SYN_SOURCE_ID,
          "N/A — synthetic", "0.4", now(), "REGISTERED"))

SYN_GEO_ID = "GEO-SYNTHETIC-ZONE03-POINT01"
cur.execute("SELECT 1 FROM geo_location WHERE geo_id=?", (SYN_GEO_ID,))
if not cur.fetchone():
    cur.execute("""
        INSERT INTO geo_location (geo_id, scope, place_name, lat, lon, crs, notes)
        VALUES (?,?,?,?,?,?,?)
    """, (SYN_GEO_ID, "POINT", "Thane Creek Zone 03 (synthetic point)", 19.2201, 72.9765,
          "EPSG:4326", "SYNTHETIC/TEST — observation-specific point per Decision B."))

conn.commit()

SYN_OBS_ID = "TC-Z03-F02-LIDAR-OBS001"  # Group 3's own example ID format from their contract

before = cur.execute("SELECT COUNT(*) FROM observation WHERE observation_id=?", (SYN_OBS_ID,)).fetchone()[0]
print(f"\n[2/3] Idempotency proof — before: {before}")

results = []
for attempt in range(1, 4):
    created = insert_observation(
        conn,
        observation_id=SYN_OBS_ID,
        dataset_id=SYN_DATASET_ID,
        geo_id=SYN_GEO_ID,
        observed_at="2026-08-19T09:14:22+00:00",  # full timestamp, Decision C
        capture_method="aerial",                    # Decision D — separate from observation_type
        species=None,
        observation_type="CANOPY_SURVEY",
        quality_status="CAPTURED",
        confidence="MEDIUM",
        measurements=[
            {"metric_name": "canopy_height", "value": 6.4, "unit": "m", "method": "lidar",
             "original_value_text": "6.4"},
        ],
        source_id=SYN_SOURCE_ID,
        run_id=SYN_RUN_ID,
        derivation_note="SYNTHETIC/TEST fixture — proves idempotency and new-field schema, not a real observation.",
        field_meta={
            "device_id": "LIDAR-UNIT-02", "operator": "SYNTHETIC_TEST", "mission_id": "F02",
            "accuracy": None, "accuracy_unit": None,   # not invented — genuinely unverified
            "accuracy_status": "NOT_VERIFIED",   # per Hemanth: checked, no spec exists (distinct from NULL = nobody filled it in)
            "calibration_status": "NOT_VERIFIED", "processing_status": "INGESTED",
        },
        raw_artifact={
            "artifact_type": "LIDAR_SCAN", "storage_ref": "synthetic://fixture/tc-z03-f02-lidar-obs001.las",
            "content_hash": None, "hash_algorithm": None,  # Rukkaiya's integrity layer populates this
            "captured_at": "2026-08-19T09:14:22+00:00", "notes": "SYNTHETIC/TEST placeholder reference.",
        },
    )
    count_now = cur.execute("SELECT COUNT(*) FROM observation WHERE observation_id=?", (SYN_OBS_ID,)).fetchone()[0]
    results.append(count_now)
    print(f"    attempt {attempt}: created={created}, row count now={count_now}")

assert results == [1, 1, 1], f"IDEMPOTENCY FAILED: expected [1,1,1], got {results}"
print(f"    RESULT: 0 -> {results[0]} -> {results[1]} -> {results[2]}. Idempotency confirmed at schema v0.2 with the new field set.")

retrieved = retrieve_observation(conn, SYN_OBS_ID)
print("\n    Retrieved synthetic record (proves new fields round-trip):")
print(json.dumps(retrieved, indent=2))

# ------------------------------------------------------------------
# 2b. IMAGE OBSERVATION — non-numeric measurement, no unit.
#     This is the exact gap Sanskar flagged: Group 3's V1.0 payload
#     includes an image observation whose "measurement" is a
#     classification label, not a number, and has no unit at all.
#     Proves data_type='TEXT' + value_text works end to end.
# ------------------------------------------------------------------
IMG_OBS_ID = "TC-Z03-F02-IMG-OBS002"
print(f"\n[2b] Image observation (non-numeric measurement) — {IMG_OBS_ID}")
img_created = insert_observation(
    conn,
    observation_id=IMG_OBS_ID,
    dataset_id=SYN_DATASET_ID,
    geo_id=SYN_GEO_ID,
    observed_at="2026-08-19T09:20:05+00:00",
    capture_method="site_evidence",
    species=None,
    observation_type="CANOPY_IMAGE",
    quality_status="CAPTURED",
    confidence="MEDIUM",
    measurements=[
        {"metric_name": "canopy_condition_classification", "data_type": "TEXT",
         "value_text": "healthy_dense_canopy", "unit": None,
         "original_value_text": "healthy_dense_canopy"},
    ],
    source_id=SYN_SOURCE_ID,
    run_id=SYN_RUN_ID,
    derivation_note="SYNTHETIC/TEST fixture — proves non-numeric measurement (data_type=TEXT) works.",
    field_meta={
        "device_id": "CAM-UNIT-01", "operator": "SYNTHETIC_TEST", "mission_id": "F02",
        "accuracy": None, "accuracy_unit": None,
        "accuracy_status": "NOT_VERIFIED",
        "calibration_status": "NOT_VERIFIED", "processing_status": "INGESTED",
    },
    raw_artifact={
        "artifact_type": "IMAGE", "storage_ref": "synthetic://fixture/tc-z03-f02-img-obs002.jpg",
        "content_hash": None, "hash_algorithm": None,
        "captured_at": "2026-08-19T09:20:05+00:00", "notes": "SYNTHETIC/TEST placeholder reference.",
    },
)
img_retrieved = retrieve_observation(conn, IMG_OBS_ID)
print(json.dumps(img_retrieved, indent=2))
assert img_created is True
assert img_retrieved["measurements"][0]["data_type"] == "TEXT"
assert img_retrieved["measurements"][0]["value"] is None
assert img_retrieved["measurements"][0]["value_text"] == "healthy_dense_canopy"
assert img_retrieved["measurements"][0]["unit"] is None
print("    RESULT: non-numeric, null-unit measurement stored and retrieved correctly.")

# ------------------------------------------------------------------
# 4. Invalid record rejection — captured, not asserted
# ------------------------------------------------------------------
print("\n[4] Invalid record rejection test:")
invalid_evidence = {
    "input": "observation with dataset_id=NULL (required field missing)",
    "expected_result": "INSERT rejected",
    "actual_result": None,
    "error": None,
    "timestamp": now(),
    "environment": "sqlite local proof (stand-in for VM Postgres)",
    "owner": "Kavy",
}
try:
    cur.execute("""
        INSERT INTO observation (observation_id, dataset_id, geo_id, observed_at,
                                  capture_method, species, observation_type,
                                  quality_status, confidence, conflict_flag, conflict_notes, created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,NULL,?)
    """, ("OBS-INVALID-TEST-001", None, None, None, None, None, None, "CAPTURED", None, False, now()))
    conn.commit()
    invalid_evidence["actual_result"] = "INSERT SUCCEEDED (unexpected)"
except Exception as e:
    conn.rollback()
    invalid_evidence["actual_result"] = "INSERT REJECTED"
    invalid_evidence["error"] = str(e)

print(json.dumps(invalid_evidence, indent=2))
assert invalid_evidence["actual_result"] == "INSERT REJECTED"

print("\n[4 continued] Artifact-only observation and provenance fix below.")

# ------------------------------------------------------------------
# 5. ARTIFACT-ONLY OBSERVATION — the actual gap found reviewing
#    Group 3's V2.1 contract. No measurement row at all — only a
#    raw_artifact (e.g. a raw RGB frame with no derived value).
#    Before the v0.6 fix, this observation would have gotten ZERO
#    provenance rows (measurement_id was NOT NULL, and there's no
#    measurement to attach to). Proves it now gets one, attached via
#    raw_artifact_id instead.
# ------------------------------------------------------------------
ARTIFACT_ONLY_OBS_ID = "TC-Z03-F02-DRONE-OBS003"
print(f"\n[5] Artifact-only observation (no measurement row) — {ARTIFACT_ONLY_OBS_ID}")
artifact_only_created = insert_observation(
    conn,
    observation_id=ARTIFACT_ONLY_OBS_ID,
    dataset_id=SYN_DATASET_ID,
    geo_id=SYN_GEO_ID,
    observed_at="2026-08-19T09:25:11+00:00",
    capture_method="aerial",
    species=None,
    observation_type="MANGROVE_RGB_IMAGE",
    quality_status="CAPTURED",
    confidence="MEDIUM",
    measurements=[],  # deliberately empty — no derived value, artifact IS the record
    source_id=SYN_SOURCE_ID,
    run_id=SYN_RUN_ID,
    derivation_note="SYNTHETIC/TEST fixture — proves artifact-only observations get provenance (v0.6 fix).",
    field_meta=None,
    raw_artifact={
        "artifact_type": "IMAGE", "storage_ref": "synthetic://fixture/tc-z03-f02-drone-obs003.jpg",
        "content_hash": None, "hash_algorithm": None,
        "captured_at": "2026-08-19T09:25:11+00:00", "notes": "SYNTHETIC/TEST — no derived measurement.",
    },
)
artifact_only_retrieved = retrieve_observation(conn, ARTIFACT_ONLY_OBS_ID)
print(json.dumps(artifact_only_retrieved, indent=2))
assert artifact_only_created is True
assert len(artifact_only_retrieved["measurements"]) == 0, "should have NO measurement rows"
assert len(artifact_only_retrieved["raw_artifacts"]) == 1
assert artifact_only_retrieved["raw_artifacts"][0]["provenance"] is not None, \
    "PRE-v0.6 BUG: this would have been None — artifact had no provenance at all"
print(f"    RESULT: artifact-only observation has 0 measurements but "
      f"{len(artifact_only_retrieved['raw_artifacts'])} raw_artifact WITH provenance "
      f"('{artifact_only_retrieved['raw_artifacts'][0]['provenance'][:50]}...'). Gap fixed.")

conn.close()
print("\n[DONE] All v0.6 evidence checks passed.")
