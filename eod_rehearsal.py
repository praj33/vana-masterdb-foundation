#!/usr/bin/env python3
"""
eod_rehearsal.py — Local EOD rehearsal for Group 1 V0.9 canonical identity and idempotency logic.

Runs against FastAPI test client:
1. Ingests a new synthetic observation with Idempotency-Key (201 CREATED)
2. Fetches GET /observations/{id} (200 OK, verifies canonical_record_id format CR-<uuid>)
3. Replays exact same request with same Idempotency-Key (200 IDEMPOTENT_REPLAY, same canonical_record_id)
4. Sends modified request with same Idempotency-Key (409 IDEMPOTENCY_CONFLICT)
5. Fetches GET /observations/{id} again (200 OK, verifies content unaltered)

SAFE: Uses synthetic test ID TC-Z03-F02-SENSOR-OBS999. Never touches TC-Z03-F02-LIDAR-OBS001 or OBS009.
"""

import json
import sys
import os
from pathlib import Path
from fastapi.testclient import TestClient

# Ensure test DB environment for standalone run
TEST_DB = Path(__file__).resolve().parent / "test_vana_eod.db"
os.environ["VANA_DATABASE_URL"] = f"sqlite:///{TEST_DB}"

if TEST_DB.exists():
    TEST_DB.unlink()

from api.db import initialize_database
initialize_database()

from api.main import app

def run_rehearsal():
    client = TestClient(app)
    
    test_obs_id = "TC-Z03-F02-SENSOR-OBS999"
    idempotency_key = "IK-TC-Z03-F02-SENSOR-OBS999"
    
    payload_1 = {
        "contract_version": "2.2",
        "schema_version": "2.2",
        "observation_id": test_obs_id,
        "source_identity": "group3-field-edge",
        "survey_id": "TC",
        "zone_id": "Z03",
        "flight_id": "F02",
        "sensor_id": "SENSOR",
        "observation_seq": "OBS999",
        "mission_id": "TC-Z03-F02",
        "observation_timestamp": "2026-08-25T10:00:00Z",
        "source_timestamp": "2026-08-25T10:00:00Z",
        "data_state": "CAPTURED",
        "synthetic_state": "CONTROLLED",
        "is_synthetic": True,
        "calibration_state": "NOT_VERIFIED",
        "quality_state": "CAPTURED",
        "location": {
            "latitude": 19.1288,
            "longitude": 72.9421,
            "altitude_m": 12.5,
            "gnss_status": "NOT_VERIFIED",
            "position_accuracy_m": None
        },
        "device_id": "G3-SENSOR-999",
        "observation_type": "canopy_height",
        "capture_method": "sensor",
        "processing_status": "raw",
        "measurement": 7.8,
        "unit": "m",
        "accuracy": "NOT_VERIFIED",
        "raw_artifact": "TC-Z03-F02/sensor/log_999.txt",
        "raw_artifact_integrity": {
            "checksum_sha256": "f7254999689ae5b530a0006d0fb6765df0317973504e8c5d1b393bfa5826cf9d",
            "hash_algorithm": "sha256",
            "artifact_type": "sensor_reading"
        },
        "provenance_reference": "TC-Z03-F02/qa/qa_F02.json",
        "provenance": {
            "device_id": "G3-SENSOR-999",
            "mission_id": "TC-Z03-F02",
            "captured_at": "2026-08-25T10:00:00Z",
            "raw_artifact": "TC-Z03-F02/sensor/log_999.txt",
            "qa_record": "TC-Z03-F02/qa/qa_F02.json"
        },
        "idempotency_key": idempotency_key,
        "hardware_verified": False
    }
    
    print("=== STARTING EOD REHEARSAL FOR V0.9 CANONICAL IDENTITY & IDEMPOTENCY ===")
    
    # 1. First POST -> 201 CREATED
    headers = {"Idempotency-Key": idempotency_key}
    res1 = client.post("/observations", json=payload_1, headers=headers)
    print(f"\n[STEP 1] Initial POST with key '{idempotency_key}':")
    print(f"Status Code: {res1.status_code}")
    print(f"Response: {json.dumps(res1.json(), indent=2)}")
    
    assert res1.status_code == 201, f"Expected 201, got {res1.status_code}"
    body1 = res1.json()
    assert body1["status"] == "ACCEPTED"
    canonical_id_1 = body1.get("canonical_record_id")
    assert canonical_id_1 is not None and canonical_id_1.startswith("CR-"), f"Invalid canonical_record_id: {canonical_id_1}"
    print(f"-> SUCCESS: Created with canonical_record_id = {canonical_id_1}")
    
    # 2. GET -> 200 OK
    res2 = client.get(f"/observations/{test_obs_id}")
    print(f"\n[STEP 2] GET /observations/{test_obs_id}:")
    print(f"Status Code: {res2.status_code}")
    print(f"Response: {json.dumps(res2.json(), indent=2)}")
    
    assert res2.status_code == 200
    body2 = res2.json()["observation"]
    assert body2["canonical_record_id"] == canonical_id_1
    print(f"-> SUCCESS: GET returned matching canonical_record_id = {canonical_id_1}")
    
    # 3. Exact Replay -> 200 IDEMPOTENT_REPLAY
    res3 = client.post("/observations", json=payload_1, headers=headers)
    print(f"\n[STEP 3] Replay exact POST with same key '{idempotency_key}':")
    print(f"Status Code: {res3.status_code}")
    print(f"Response: {json.dumps(res3.json(), indent=2)}")
    
    assert res3.status_code == 200, f"Expected 200, got {res3.status_code}"
    body3 = res3.json()
    assert body3["status"] == "IDEMPOTENT_REPLAY"
    assert body3.get("canonical_record_id") == canonical_id_1
    print(f"-> SUCCESS: Replay returned 200 with identical canonical_record_id = {canonical_id_1}")
    
    # 4. Mutated Replay -> 409 IDEMPOTENCY_CONFLICT
    payload_mutated = dict(payload_1)
    payload_mutated["measurement"] = 15.0  # Mutated measurement
    res4 = client.post("/observations", json=payload_mutated, headers=headers)
    print(f"\n[STEP 4] POST mutated payload with same key '{idempotency_key}':")
    print(f"Status Code: {res4.status_code}")
    print(f"Response: {json.dumps(res4.json(), indent=2)}")
    
    assert res4.status_code == 409, f"Expected 409, got {res4.status_code}"
    body4 = res4.json()
    assert body4["status"] == "IDEMPOTENCY_CONFLICT"
    assert body4.get("canonical_record_id") is None
    print("-> SUCCESS: Mutated payload returned 409 IDEMPOTENCY_CONFLICT")
    
    # 5. Final GET -> 200 OK (unaltered)
    res5 = client.get(f"/observations/{test_obs_id}")
    print(f"\n[STEP 5] Final GET /observations/{test_obs_id}:")
    print(f"Status Code: {res5.status_code}")
    body5 = res5.json()["observation"]
    assert body5["measurements"][0]["value"] == 7.8, "Measurement value was mutated!"
    assert body5["canonical_record_id"] == canonical_id_1
    print("-> SUCCESS: Observation content remains original and uncorrupted.")
    
    print("\n=== ALL EOD REHEARSAL STEPS PASSED SUCCESSFULLY ===")

    if TEST_DB.exists():
        TEST_DB.unlink()

if __name__ == "__main__":
    run_rehearsal()
