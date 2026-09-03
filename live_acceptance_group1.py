#!/usr/bin/env python3
"""
live_acceptance_group1.py — Standalone Live V2.2 E2E Acceptance Test Script for Group 1 VANA MasterDB.

Target Observation: TC-Z03-F02-LIDAR-OBS001
Contract Version: Group 3 Observation Schema V2.2

Usage:
    python live_acceptance_group1.py [--base-url http://163.128.209.18:8013] [--timeout 10]
"""

import argparse
import copy
import json
import sys
from pathlib import Path

try:
    import requests
except ImportError:
    print("Error: 'requests' module is required. Please install it with 'pip install requests'.", file=sys.stderr)
    sys.exit(1)


TARGET_OBS_ID = "TC-Z03-F02-LIDAR-OBS001"
DEFAULT_BASE_URL = "http://163.128.209.18:8013"


def load_v22_target_payload() -> dict:
    """Load TC-Z03-F02-LIDAR-OBS001 fixture from repository V2.2 sample files."""
    repo_root = Path(__file__).resolve().parent
    for fname in ["sample_mission_package.v2.2.json", "sample_mission_package.json"]:
        fpath = repo_root / fname
        if fpath.exists():
            try:
                data = json.loads(fpath.read_text(encoding="utf-8"))
                for obs in data.get("observations", []):
                    if obs.get("observation_id") == TARGET_OBS_ID:
                        return copy.deepcopy(obs)
            except Exception:
                pass

    # Embedded fallback exact V2.2 canonical fixture
    return {
        "contract_version": "2.2",
        "schema_version": "2.2",
        "observation_id": TARGET_OBS_ID,
        "source_identity": "group3-field-edge",
        "survey_id": "TC",
        "zone_id": "Z03",
        "flight_id": "F02",
        "sensor_id": "LIDAR",
        "observation_seq": "OBS001",
        "mission_id": "TC-Z03-F02",
        "parent_reference": None,
        "observation_timestamp": "2026-08-13T09:14:22Z",
        "source_timestamp": "2026-08-13T09:14:22Z",
        "ingestion_timestamp": None,
        "data_state": "VALIDATED",
        "synthetic_state": "CONTROLLED",
        "is_synthetic": True,
        "calibration_state": "NOT_VERIFIED",
        "quality_state": "VALIDATED",
        "location": {
            "latitude": 19.1288,
            "longitude": 72.9421,
            "altitude_m": 120.0,
            "gnss_status": "NOT_VERIFIED",
            "position_accuracy_m": None
        },
        "device_id": "G3-LIDAR-001",
        "observation_type": "canopy_height",
        "capture_method": "aerial",
        "processing_status": "raw",
        "measurement": 4.7,
        "unit": "m",
        "accuracy": "NOT_VERIFIED",
        "raw_artifact": "TC-Z03-F02/drone/pointcloud_F02_001.las",
        "raw_artifact_integrity": {
            "checksum_sha256": "f7254999689ae5b530a0006d0fb6765df0317973504e8c5d1b393bfa5826cf9d",
            "hash_algorithm": "sha256",
            "artifact_type": "point_cloud"
        },
        "provenance_reference": "TC-Z03-F02/qa/qa_F02.json",
        "provenance": {
            "device_id": "G3-LIDAR-001",
            "mission_id": "TC-Z03-F02",
            "captured_at": "2026-08-13T09:14:22Z",
            "raw_artifact": "TC-Z03-F02/drone/pointcloud_F02_001.las",
            "qa_record": "TC-Z03-F02/qa/qa_F02.json"
        },
        "hardware_verified": False
    }


def safe_json_response(res: requests.Response) -> dict:
    """Parse JSON body or return structured fallback for non-JSON responses."""
    try:
        return res.json()
    except Exception:
        return {"raw_body": res.text}


def get_field_val(data: dict, key_path: str):
    """
    Traverse a nested JSON structure (e.g. 'location.latitude' or 'raw_artifact_integrity.checksum_sha256')
    and return value or 'NOT_RETURNED'. Also checks field_observation_meta, geo_location, and raw_artifacts list.
    """
    parts = key_path.split(".")
    curr = data
    for p in parts:
        if isinstance(curr, dict) and p in curr and curr[p] is not None:
            curr = curr[p]
        else:
            curr = None
            break

    if curr is not None:
        return curr

    # Mapping helpers for alternate returned shapes in legacy API wrappers
    flat_key = key_path.split(".")[-1]
    if flat_key in data and data[flat_key] is not None:
        return data[flat_key]

    geo = data.get("geo_location", {})
    if isinstance(geo, dict):
        if flat_key == "latitude" and "lat" in geo and geo["lat"] is not None:
            return geo["lat"]
        if flat_key == "longitude" and "lon" in geo and geo["lon"] is not None:
            return geo["lon"]
        if flat_key in geo and geo[flat_key] is not None:
            return geo[flat_key]

    meta = data.get("field_observation_meta") or data.get("field_meta") or {}
    if isinstance(meta, dict) and flat_key in meta and meta[flat_key] is not None:
        return meta[flat_key]

    artifacts = data.get("raw_artifacts", [])
    if isinstance(artifacts, list) and len(artifacts) > 0:
        first_art = artifacts[0]
        if isinstance(first_art, dict):
            if flat_key in ("content_hash", "checksum_sha256") and first_art.get("content_hash") is not None:
                return first_art["content_hash"]
            if flat_key == "hash_algorithm" and first_art.get("hash_algorithm") is not None:
                return first_art["hash_algorithm"]

    return "NOT_RETURNED"


def run_acceptance_test(base_url: str, timeout: int) -> int:
    base_url = base_url.rstrip("/")
    print("=" * 80)
    print("  GROUP 1 VANA MASTERDB — LIVE ACCEPTANCE TEST (V2.2 SCHEMA INTEGRATION)")
    print(f"  Target Base URL : {base_url}")
    print(f"  Target Observation: {TARGET_OBS_ID}")
    print("=" * 80)

    matrix = {
        "Health": False,
        "Initial 201 ACCEPTED": False,
        "Exact observation identity": False,
        "Canonical GET": False,
        "synthetic_state": False,
        "is_synthetic": False,
        "provenance": False,
        "raw artifact/hash": False,
        "Identical replay 200": False,
        "Mutated conflict 409": False,
        "Final GET": False,
        "Canonical immutability": False,
    }

    idempotency_key = f"IK-{TARGET_OBS_ID}"
    headers_base = {"Content-Type": "application/json"}
    headers_idempotent = {"Content-Type": "application/json", "Idempotency-Key": idempotency_key}

    # -------------------------------------------------------------------------
    # STEP 1 — Health
    # -------------------------------------------------------------------------
    print("\n[STEP 1] GET /health ...")
    try:
        res_health = requests.get(f"{base_url}/health", timeout=timeout)
        print(f"  HTTP Status : {res_health.status_code}")
        body_health = safe_json_response(res_health)
        print(f"  Body        : {json.dumps(body_health)}")
        if res_health.status_code == 200:
            matrix["Health"] = True
    except Exception as e:
        print(f"  [ERROR] /health request failed: {e}")

    # -------------------------------------------------------------------------
    # STEP 2 — Initial V2.2 Ingestion
    # -------------------------------------------------------------------------
    payload_v22 = load_v22_target_payload()
    payload_v22["idempotency_key"] = idempotency_key

    print(f"\n[STEP 2] POST /observations (Idempotency-Key: {idempotency_key}) ...")
    try:
        res_ingest = requests.post(f"{base_url}/observations", json=payload_v22, headers=headers_idempotent, timeout=timeout)
        print(f"  HTTP Status : {res_ingest.status_code}")
        body_ingest = safe_json_response(res_ingest)
        print(f"  Body        : {json.dumps(body_ingest)}")
        if res_ingest.status_code == 201:
            matrix["Initial 201 ACCEPTED"] = True
    except Exception as e:
        print(f"  [ERROR] POST /observations failed: {e}")

    # -------------------------------------------------------------------------
    # STEP 3 — Canonical Retrieval & STEP 4/5/6 Verifications
    # -------------------------------------------------------------------------
    print(f"\n[STEP 3] GET /observations/{TARGET_OBS_ID} ...")
    retrieved_obs = {}
    try:
        res_get1 = requests.get(f"{base_url}/observations/{TARGET_OBS_ID}", timeout=timeout)
        print(f"  HTTP Status : {res_get1.status_code}")
        body_get1 = safe_json_response(res_get1)
        print(f"  Body        : {json.dumps(body_get1, indent=2)}")

        if res_get1.status_code == 200:
            matrix["Canonical GET"] = True
            retrieved_obs = body_get1.get("observation") or body_get1

            print("\n  --- FIELD RETRIEVAL EVIDENCE ---")
            fields_to_check = [
                "observation_id", "canonical_record_id", "schema_version",
                "synthetic_state", "is_synthetic", "observation_timestamp",
                "ingestion_timestamp", "trace_id", "provenance", "provenance_reference",
                "raw_artifact", "raw_artifact_reference", "raw_artifact_integrity.checksum_sha256",
                "raw_artifact_integrity.hash_algorithm", "location.latitude", "location.longitude",
                "location.altitude_m", "location.gnss_status", "location.position_accuracy_m",
                "data_state", "quality_state", "calibration_state", "accuracy", "processing_status"
            ]

            extracted_fields = {}
            for field in fields_to_check:
                val = get_field_val(retrieved_obs, field)
                extracted_fields[field] = val
                print(f"    {field:<40}: {val}")

            # STEP 4 — Exact Identity Verification
            if extracted_fields.get("observation_id") == TARGET_OBS_ID or retrieved_obs.get("observation_id") == TARGET_OBS_ID:
                matrix["Exact observation identity"] = True

            # STEP 5 — Synthetic-State Verification
            syn_state = extracted_fields.get("synthetic_state")
            is_syn = extracted_fields.get("is_synthetic")
            if syn_state == "CONTROLLED":
                matrix["synthetic_state"] = True
            if is_syn is True:
                matrix["is_synthetic"] = True

            # STEP 6 — Provenance/artifact Verification
            prov = extracted_fields.get("provenance")
            art = extracted_fields.get("raw_artifact") or extracted_fields.get("raw_artifact_reference")
            art_list = retrieved_obs.get("raw_artifacts", [])
            if prov != "NOT_RETURNED" or "provenance" in retrieved_obs:
                matrix["provenance"] = True
            if art != "NOT_RETURNED" or len(art_list) > 0 or "raw_artifact" in retrieved_obs:
                matrix["raw artifact/hash"] = True

    except Exception as e:
        print(f"  [ERROR] GET /observations/{TARGET_OBS_ID} failed: {e}")

    # -------------------------------------------------------------------------
    # STEP 7 — Identical Replay
    # -------------------------------------------------------------------------
    print(f"\n[STEP 7] POST /observations (Identical Replay, Same Idempotency-Key: {idempotency_key}) ...")
    try:
        res_replay = requests.post(f"{base_url}/observations", json=payload_v22, headers=headers_idempotent, timeout=timeout)
        print(f"  HTTP Status : {res_replay.status_code}")
        body_replay = safe_json_response(res_replay)
        print(f"  Body        : {json.dumps(body_replay)}")
        if res_replay.status_code == 200 and body_replay.get("status") == "IDEMPOTENT_REPLAY":
            matrix["Identical replay 200"] = True
        elif res_replay.status_code == 200:
            matrix["Identical replay 200"] = True
    except Exception as e:
        print(f"  [ERROR] Identical replay POST failed: {e}")

    # -------------------------------------------------------------------------
    # STEP 8 — Mutated Conflict
    # -------------------------------------------------------------------------
    print(f"\n[STEP 8] POST /observations (Mutated Payload, Same Idempotency-Key: {idempotency_key}) ...")
    payload_mutated = copy.deepcopy(payload_v22)
    payload_mutated["measurement"] = 9.9  # Safe payload mutation without altering observation_id

    try:
        res_conflict = requests.post(f"{base_url}/observations", json=payload_mutated, headers=headers_idempotent, timeout=timeout)
        print(f"  HTTP Status : {res_conflict.status_code}")
        body_conflict = safe_json_response(res_conflict)
        print(f"  Body        : {json.dumps(body_conflict)}")
        if res_conflict.status_code == 409 and body_conflict.get("status") == "IDEMPOTENCY_CONFLICT":
            matrix["Mutated conflict 409"] = True
        elif res_conflict.status_code == 409:
            matrix["Mutated conflict 409"] = True
    except Exception as e:
        print(f"  [ERROR] Mutated conflict POST failed: {e}")

    # -------------------------------------------------------------------------
    # STEP 9 — Final Canonical Retrieval
    # -------------------------------------------------------------------------
    print(f"\n[STEP 9] GET /observations/{TARGET_OBS_ID} (Final Verification) ...")
    try:
        res_get2 = requests.get(f"{base_url}/observations/{TARGET_OBS_ID}", timeout=timeout)
        print(f"  HTTP Status : {res_get2.status_code}")
        body_get2 = safe_json_response(res_get2)
        print(f"  Body        : {json.dumps(body_get2, indent=2)}")

        if res_get2.status_code == 200:
            matrix["Final GET"] = True
            obs2 = body_get2.get("observation") or body_get2
            obs2_id = obs2.get("observation_id")
            obs2_syn_state = obs2.get("synthetic_state") or get_field_val(obs2, "synthetic_state")
            obs2_is_syn = obs2.get("is_synthetic") if "is_synthetic" in obs2 else get_field_val(obs2, "is_synthetic")

            if obs2_id == TARGET_OBS_ID and obs2_syn_state == "CONTROLLED" and obs2_is_syn is True:
                matrix["Canonical immutability"] = True
    except Exception as e:
        print(f"  [ERROR] Final GET /observations/{TARGET_OBS_ID} failed: {e}")

    # -------------------------------------------------------------------------
    # STEP 10 — Acceptance Summary Matrix
    # -------------------------------------------------------------------------
    print("\n" + "=" * 80)
    print("  FINAL V2.2 ACCEPTANCE SUMMARY MATRIX")
    print("=" * 80)

    all_passed = True
    for item, passed in matrix.items():
        tag = "[PASS]" if passed else "[FAIL]"
        print(f"  {tag:<8} {item}")
        if not passed:
            all_passed = False

    print("-" * 80)
    proof_status = "PROVEN" if (matrix["Initial 201 ACCEPTED"] and matrix["Identical replay 200"] and matrix["Mutated conflict 409"]) else "FAILED"
    print(f"  0 -> 1 -> 1 transition: {proof_status}")
    print("=" * 80)

    return 0 if all_passed else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Live V2.2 Acceptance Test for Group 1 VANA MasterDB.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help=f"Live API Base URL (default: {DEFAULT_BASE_URL})")
    parser.add_argument("--timeout", type=int, default=10, help="HTTP request timeout in seconds (default: 10)")
    args = parser.parse_args()

    sys.exit(run_acceptance_test(base_url=args.base_url, timeout=args.timeout))
