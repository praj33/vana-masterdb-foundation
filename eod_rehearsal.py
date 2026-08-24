#!/usr/bin/env python3
"""
eod_rehearsal.py — proves the exact sequence Raj's Group 1 Final EOD
brief requires, BEFORE the real Group 3 observation exists:

    201 CREATED -> GET 200 -> replay 200 -> conflict 409 -> final GET 200

*** THIS IS A REHEARSAL, NOT TODAY'S DEMO RECORD ***
Uses a clearly-synthetic observation_id that does NOT match OBS001 or
OBS009 (both explicitly banned in the brief). When Group 3's real
approved non-LiDAR observation arrives, swap REHEARSAL_PAYLOAD below
for the real payload and re-run — same script, same proof, real data.

Run after init_db.py:
    python3 init_db.py && python3 eod_rehearsal.py
"""

import json
import hashlib
from vana_db import get_conn, ingest_with_idempotency, retrieve_observation, now

conn = get_conn()
cur = conn.cursor()

# ------------------------------------------------------------------
# Prerequisite rows (source/dataset/geo) — same pattern as seed.py,
# scoped to this rehearsal so it doesn't collide with real data.
# ------------------------------------------------------------------
REH_SOURCE_ID = "SRC-REHEARSAL-EOD-NONLIDAR-01"
cur.execute("SELECT 1 FROM source WHERE source_id=?", (REH_SOURCE_ID,))
if not cur.fetchone():
    cur.execute("""
        INSERT INTO source (source_id, source_type, title, publisher, url, citation,
                             retrieved_at, is_synthetic, notes)
        VALUES (?,?,?,?,?,?,?,?,?)
    """, (REH_SOURCE_ID, "SYNTHETIC_TEST", "EOD rehearsal fixture — non-LiDAR sensor reading",
          None, None, None, now(), True, "SYNTHETIC/TEST — rehearsal only, not a real Group 3 submission."))

REH_RUN_ID = "RUN-EOD-REHEARSAL-001"
cur.execute("SELECT 1 FROM processing_run WHERE run_id=?", (REH_RUN_ID,))
if not cur.fetchone():
    cur.execute("""
        INSERT INTO processing_run (run_id, source_id, dataset_id, pipeline_stage, status,
                                     input_ref, output_ref, error_detail, started_at, finished_at, actor)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
    """, (REH_RUN_ID, REH_SOURCE_ID, None, "EOD_REHEARSAL", "DONE",
          "rehearsal fixture", "canonical_record_id + replay/conflict proof", None, now(), now(),
          "Kavy (EOD rehearsal, ahead of real Group 3 payload)"))

REH_DATASET_ID = "DS-REHEARSAL-EOD-NONLIDAR-01"
cur.execute("SELECT 1 FROM dataset WHERE dataset_id=?", (REH_DATASET_ID,))
if not cur.fetchone():
    cur.execute("""
        INSERT INTO dataset (dataset_id, dataset_name, source_id, methodology,
                              schema_version, created_at, status)
        VALUES (?,?,?,?,?,?,?)
    """, (REH_DATASET_ID, "EOD rehearsal dataset — non-LiDAR", REH_SOURCE_ID,
          "N/A — rehearsal", "0.9", now(), "REGISTERED"))

REH_GEO_ID = "GEO-REHEARSAL-EOD-01"
cur.execute("SELECT 1 FROM geo_location WHERE geo_id=?", (REH_GEO_ID,))
if not cur.fetchone():
    cur.execute("""
        INSERT INTO geo_location (geo_id, scope, place_name, lat, lon, crs, notes)
        VALUES (?,?,?,?,?,?,?)
    """, (REH_GEO_ID, "POINT", "Thane Creek (rehearsal point)", 19.2195, 72.9770, "EPSG:4326",
          "SYNTHETIC/TEST — rehearsal only."))

conn.commit()

# ------------------------------------------------------------------
# The observation itself — deliberately NOT ending in OBS001/OBS009.
# Non-LiDAR: a water-quality sensor reading, capture_method='sensor'.
# ------------------------------------------------------------------
REHEARSAL_OBS_ID = "TC-Z03-F05-SENSOR-REHEARSAL-A1"

REHEARSAL_PAYLOAD = dict(
    observation_id=REHEARSAL_OBS_ID,
    dataset_id=REH_DATASET_ID,
    geo_id=REH_GEO_ID,
    observed_at="2026-08-21T14:20:00+00:00",
    capture_method="sensor",              # non-LiDAR
    species=None,
    observation_type="WATER_QUALITY",
    quality_status="CAPTURED",
    confidence="MEDIUM",
    measurements=[
        {"metric_name": "dissolved_oxygen", "value": 5.2, "unit": "mg/L", "method": "sensor_probe",
         "original_value_text": "5.2"},
    ],
    source_id=REH_SOURCE_ID,
    run_id=REH_RUN_ID,
    derivation_note="SYNTHETIC/TEST rehearsal fixture — proves 201/200/replay/409/final-200 sequence ahead of real Group 3 payload.",
    is_synthetic=True,
    synthetic_state="SYNTHETIC",
    field_meta={
        "device_id": "WQ-SENSOR-05", "operator": "SYNTHETIC_TEST", "mission_id": "F05",
        "accuracy": None, "accuracy_unit": None, "accuracy_status": "NOT_VERIFIED",
        "calibration_status": "NOT_VERIFIED", "processing_status": "INGESTED",
    },
)

def fingerprint(payload):
    canonical = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()

IDEMPOTENCY_KEY = "eod-rehearsal-key-001"
fp_original = fingerprint(REHEARSAL_PAYLOAD)

print("=" * 70)
print("*** REHEARSAL ONLY — NOT today's real Group 3 demo record ***")
print(f"observation_id: {REHEARSAL_OBS_ID}  (deliberately not OBS001/OBS009)")
print("=" * 70)

# 1. CREATE — expect 201
r1 = ingest_with_idempotency(conn, idempotency_key=IDEMPOTENCY_KEY,
                              request_fingerprint=fp_original, **REHEARSAL_PAYLOAD)
print(f"\n[1] CREATE -> status={r1['status']} canonical_record_id={r1['canonical_record_id']}")
assert r1["status"] == 201, r1
canonical_id = r1["canonical_record_id"]

# 2. GET — expect 200, full record
record = retrieve_observation(conn, REHEARSAL_OBS_ID)
print(f"[2] GET -> canonical_record_id={record['canonical_record_id']}")
assert record is not None
assert record["canonical_record_id"] == canonical_id

# 3. REPLAY — same key, same fingerprint -> expect 200, SAME canonical_record_id
r3 = ingest_with_idempotency(conn, idempotency_key=IDEMPOTENCY_KEY,
                              request_fingerprint=fp_original, **REHEARSAL_PAYLOAD)
print(f"[3] REPLAY -> status={r3['status']} canonical_record_id={r3['canonical_record_id']}")
assert r3["status"] == 200, r3
assert r3["canonical_record_id"] == canonical_id, "REPLAY REGENERATED canonical_record_id — this must never happen"

# 4. CONFLICT — same key, DIFFERENT fingerprint (simulate a changed payload) -> expect 409
mutated_payload = dict(REHEARSAL_PAYLOAD)
mutated_payload["measurements"] = [
    {"metric_name": "dissolved_oxygen", "value": 9.9, "unit": "mg/L", "method": "sensor_probe",
     "original_value_text": "9.9"},
]
fp_mutated = fingerprint(mutated_payload)
r4 = ingest_with_idempotency(conn, idempotency_key=IDEMPOTENCY_KEY,
                              request_fingerprint=fp_mutated, **REHEARSAL_PAYLOAD)
print(f"[4] CONFLICT -> status={r4['status']} reason={r4['reason'][:80]}...")
assert r4["status"] == 409, r4

# 5. FINAL GET — must still return the ORIGINAL, unmutated record
final_record = retrieve_observation(conn, REHEARSAL_OBS_ID)
print(f"[5] FINAL GET -> canonical_record_id={final_record['canonical_record_id']}, "
      f"dissolved_oxygen={final_record['measurements'][0]['value']}")
assert final_record["canonical_record_id"] == canonical_id
assert final_record["measurements"][0]["value"] == 5.2, "Conflict attempt MUTATED the original record — must not happen"

print("\n" + "=" * 70)
print("SEQUENCE CONFIRMED: 201 -> 200 -> 200(replay) -> 409(conflict) -> 200(final)")
print(f"canonical_record_id stable throughout: {canonical_id}")
print("*** Swap REHEARSAL_PAYLOAD for the real Group 3 non-LiDAR observation and re-run for the actual EOD proof. ***")
print("=" * 70)

conn.close()
