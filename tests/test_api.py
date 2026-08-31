import json
import os
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


# Use a dedicated SQLite database for API integration tests.
TEST_DB = Path(__file__).resolve().parents[1] / "test_vana_api.db"
os.environ["VANA_DATABASE_URL"] = f"sqlite:///{TEST_DB}"


from api.db import initialize_database
from api.main import app


ROOT = Path(__file__).resolve().parents[1]
client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_database():
    if TEST_DB.exists():
        TEST_DB.unlink()

    initialize_database()

    yield

    if TEST_DB.exists():
        TEST_DB.unlink()


def load_observations():
    p = ROOT / "sample_mission_package.v2.2.json"
    if not p.exists():
        p = ROOT / "sample_mission_package.json"
    with p.open(
        "r",
        encoding="utf-8",
    ) as f:
        return json.load(f)["observations"]


def test_health():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_valid_observation_is_persisted():
    observation = load_observations()[0]

    response = client.post(
        "/observations",
        json=observation,
    )

    assert response.status_code == 201
    assert response.json()["observation_id"] == observation["observation_id"]
    assert response.json()["status"] == "ACCEPTED"

    conn = sqlite3.connect(TEST_DB)

    row = conn.execute(
        """
        SELECT observation_id
        FROM observation
        WHERE observation_id = ?
        """,
        (observation["observation_id"],),
    ).fetchone()

    conn.close()

    assert row is not None
    assert row[0] == observation["observation_id"]


def test_observation_can_be_retrieved_from_canonical_persistence():
    observation = load_observations()[1]

    response = client.post(
        "/observations",
        json=observation,
    )

    assert response.status_code == 201

    retrieved = client.get(
        f"/observations/{observation['observation_id']}"
    )

    assert retrieved.status_code == 200
    assert retrieved.json()["status"] == "RETRIEVED"

    persisted = retrieved.json()["observation"]

    assert persisted["observation_id"] == observation["observation_id"]
    assert persisted["observed_at"] == (observation.get("observation_timestamp") or observation.get("timestamp"))
    assert persisted["observation_type"] == observation["observation_type"]


def test_invalid_observation_is_rejected():
    observation = load_observations()[0].copy()
    if "observation_timestamp" in observation:
        del observation["observation_timestamp"]
    if "timestamp" in observation:
        del observation["timestamp"]

    response = client.post(
        "/observations",
        json=observation,
    )

    assert response.status_code == 400
    assert response.json()["status"] == "REJECTED"
    assert response.json()["errors"]


def test_duplicate_observation_is_idempotent_replay():
    observation = load_observations()[2]

    first = client.post(
        "/observations",
        json=observation,
    )

    second = client.post(
        "/observations",
        json=observation,
    )

    assert first.status_code == 201
    assert first.json()["status"] == "ACCEPTED"

    assert second.status_code == 200
    assert second.json()["status"] == "IDEMPOTENT_REPLAY"

    assert (
        second.json()["observation_id"]
        == observation["observation_id"]
    )


def test_idempotent_replay_returns_200():
    observation = load_observations()[0]

    first = client.post(
        "/observations",
        json=observation,
    )

    second = client.post(
        "/observations",
        json=observation,
    )

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json()["status"] == "IDEMPOTENT_REPLAY"
    assert (
        second.json()["observation_id"]
        == observation["observation_id"]
    )


def test_idempotency_conflict_is_rejected():
    observation = load_observations()[0].copy()

    first = client.post(
        "/observations",
        json=observation,
    )

    assert first.status_code == 201

    conflicting = observation.copy()
    conflicting["measurement"] = 999.9

    second = client.post(
        "/observations",
        json=conflicting,
    )

    assert second.status_code == 409
    assert second.json()["status"] == "IDEMPOTENCY_CONFLICT"


def test_missing_observation_returns_404():
    response = client.get(
        "/observations/DOES-NOT-EXIST"
    )

    assert response.status_code == 404
    assert response.json()["status"] == "NOT_FOUND"


def test_uncertain_observation_with_null_coordinates_is_accepted():
    observation = load_observations()[2]

    response = client.post(
        "/observations",
        json=observation,
    )

    assert response.status_code == 201
    assert response.json()["status"] == "ACCEPTED"

    conn = sqlite3.connect(TEST_DB)

    row = conn.execute(
        """
        SELECT geo_id, quality_status
        FROM observation
        WHERE observation_id = ?
        """,
        (observation["observation_id"],),
    ).fetchone()

    conn.close()

    assert row is not None
    assert row[0] is None
    assert row[1] == "UNCERTAIN"


def test_not_verified_accuracy_is_accepted():
    observation = load_observations()[0].copy()

    assert observation.get("accuracy") in ("NOT VERIFIED", "NOT_VERIFIED")

    response = client.post(
        "/observations",
        json=observation,
    )

    assert response.status_code == 201


def test_missing_raw_artifact_reference_is_rejected():
    observation = load_observations()[0].copy()
    if "raw_artifact_reference" in observation:
        del observation["raw_artifact_reference"]
    if "raw_artifact" in observation:
        del observation["raw_artifact"]

    response = client.post(
        "/observations",
        json=observation,
    )

    assert response.status_code == 400
    assert response.json()["status"] == "REJECTED"
    assert response.json()["errors"]


def test_missing_provenance_is_rejected():
    observation = load_observations()[0].copy()
    del observation["provenance"]

    response = client.post(
        "/observations",
        json=observation,
    )

    assert response.status_code == 400
    assert response.json()["status"] == "REJECTED"


def test_malformed_observation_id_is_rejected():
    observation = load_observations()[0].copy()
    observation["observation_id"] = "not-an-id"

    response = client.post(
        "/observations",
        json=observation,
    )

    assert response.status_code == 400
    assert response.json()["status"] == "REJECTED"


def test_unexpected_field_is_rejected():
    observation = load_observations()[0].copy()
    observation["injected_field"] = "x"

    response = client.post(
        "/observations",
        json=observation,
    )

    assert response.status_code == 400
    assert response.json()["status"] == "REJECTED"


def test_acceptance_001_idempotency_proof_header():
    observation = load_observations()[0].copy()
    if "idempotency_key" in observation:
        del observation["idempotency_key"]
    headers = {"Idempotency-Key": "test-key-acceptance-001"}

    conn = sqlite3.connect(TEST_DB)
    before_count = conn.execute("SELECT COUNT(*) FROM observation").fetchone()[0]
    conn.close()
    assert before_count == 0

    first = client.post("/observations", json=observation, headers=headers)
    assert first.status_code == 201
    assert first.json()["status"] == "ACCEPTED"

    conn = sqlite3.connect(TEST_DB)
    first_count = conn.execute("SELECT COUNT(*) FROM observation").fetchone()[0]
    conn.close()
    assert first_count == 1

    second = client.post("/observations", json=observation, headers=headers)
    assert second.status_code == 200
    assert second.json()["status"] == "IDEMPOTENT_REPLAY"

    conn = sqlite3.connect(TEST_DB)
    second_count = conn.execute("SELECT COUNT(*) FROM observation").fetchone()[0]
    conn.close()
    assert second_count == 1

    mutated = observation.copy()
    mutated["observation_type"] = "MUTATED_CANOPY_SURVEY"
    third = client.post("/observations", json=mutated, headers=headers)
    assert third.status_code == 409
    assert third.json()["status"] == "IDEMPOTENCY_CONFLICT"

    conn = sqlite3.connect(TEST_DB)
    third_count = conn.execute("SELECT COUNT(*) FROM observation").fetchone()[0]
    conn.close()
    assert third_count == 1


def test_duplicate_submission_without_key_returns_409_duplicate():
    observation = load_observations()[0].copy()
    observation["observation_id"] = "TC-Z03-F02-LIDAR-OBS099"
    observation["observation_seq"] = "OBS099"
    if "idempotency_key" in observation:
        del observation["idempotency_key"]

    first = client.post("/observations", json=observation)
    assert first.status_code == 201

    second = client.post("/observations", json=observation)
    assert second.status_code == 409
    assert second.json()["status"] == "DUPLICATE"


def test_deterministic_child_ids_and_decision_d_mapping():
    observation = load_observations()[0].copy()
    observation["observation_id"] = "TC-Z03-F02-LIDAR-OBS088"
    observation["observation_seq"] = "OBS088"
    observation["idempotency_key"] = "IK-TC-Z03-F02-LIDAR-OBS088"

    res = client.post("/observations", json=observation)
    assert res.status_code == 201

    retrieved = client.get("/observations/TC-Z03-F02-LIDAR-OBS088")
    assert retrieved.status_code == 200
    data = retrieved.json()["observation"]

    assert data["capture_method"] == "aerial"
    assert data["observation_type"] == "canopy_height"

    conn = sqlite3.connect(TEST_DB)
    meas = conn.execute("SELECT measurement_id FROM measurement WHERE observation_id = ?", ("TC-Z03-F02-LIDAR-OBS088",)).fetchone()
    art = conn.execute("SELECT artifact_id FROM raw_artifact WHERE observation_id = ?", ("TC-Z03-F02-LIDAR-OBS088",)).fetchone()
    run = conn.execute("SELECT run_id FROM processing_run WHERE output_ref = ?", ("TC-Z03-F02-LIDAR-OBS088",)).fetchone()
    prov = conn.execute("SELECT provenance_id FROM provenance WHERE measurement_id = ?", (meas[0],)).fetchone()
    conn.close()

    assert meas[0].startswith("MEAS-")
    assert art[0].startswith("ART-")
    assert run[0].startswith("RUN-")
    assert prov[0].startswith("PROV-")


def test_v21_full_payload_ingestion_and_retrieval():
    payload = {
        "observation_id": "TC-Z03-F02-SENSOR-OBS201",
        "device_id": "G3-SENSOR-999",
        "timestamp": "2026-08-19T12:00:00Z",
        "latitude": 19.0456,
        "longitude": 72.8891,
        "is_synthetic": True,
        "capture_method": "sensor",
        "quality_state": "VALIDATED",
        "calibration_state": "CALIBRATED",
        "location": {
            "latitude": 19.0456,
            "longitude": 72.8891,
            "altitude_m": 12.5,
            "gnss_status": "FIX",
            "position_accuracy_m": 0.3
        },
        "parameter": "soil_moisture",
        "measurement": 42.1,
        "unit": "%",
        "accuracy": 0.1,
        "raw_artifact_reference": {
            "path": "sensor_logs/log_201.txt",
            "artifact_type": "sensor_reading",
            "checksum_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        },
        "processing_status": "raw",
        "provenance": {
            "device_id": "G3-SENSOR-999",
            "mission_id": "TC-Z03-F02",
            "captured_at": "2026-08-19T12:00:00Z",
            "raw_artifact": "sensor_logs/log_201.txt"
        },
        "tidal_state": "high",
        "idempotency_key": "IK-TC-Z03-F02-SENSOR-OBS201"
    }

    res = client.post("/observations", json=payload)
    assert res.status_code == 201
    assert res.json()["status"] == "ACCEPTED"

    retrieved = client.get("/observations/TC-Z03-F02-SENSOR-OBS201")
    assert retrieved.status_code == 200
    data = retrieved.json()["observation"]

    assert data["observation_id"] == "TC-Z03-F02-SENSOR-OBS201"
    assert data["is_synthetic"] is True
    assert data["capture_method"] == "sensor"
    assert data["quality_status"] == "VALIDATED"
    assert data["geo_location"]["latitude"] == 19.0456
    assert data["geo_location"]["longitude"] == 72.8891
    assert data["geo_location"]["altitude_m"] == 12.5
    assert data["geo_location"]["place_name"] == "Group 3 observation location"
    assert data["geo_location"]["place_name"] != data["synthetic_state"]
    assert data["geo_location"]["crs"] == "EPSG:4326"
    assert data["field_observation_meta"]["calibration_status"] == "CALIBRATED"
    assert data["field_observation_meta"]["gnss_status"] == "FIX"
    assert data["field_observation_meta"]["position_accuracy_m"] == 0.3


def test_geo_location_retrieval_mapping_regression():
    payload = {
        "contract_version": "2.2",
        "schema_version": "2.2",
        "observation_id": "TC-Z03-F02-SENSOR-OBS205",
        "source_identity": "group3-field-edge",
        "survey_id": "TC",
        "zone_id": "Z03",
        "flight_id": "F02",
        "sensor_id": "SENSOR",
        "observation_seq": "OBS205",
        "mission_id": "TC-Z03-F02",
        "observation_timestamp": "2026-08-26T10:00:00Z",
        "source_timestamp": "2026-08-26T10:00:00Z",
        "data_state": "CAPTURED",
        "synthetic_state": "CONTROLLED",
        "is_synthetic": True,
        "calibration_state": "NOT_VERIFIED",
        "quality_state": "CAPTURED",
        "location": {
            "latitude": 19.1288,
            "longitude": 72.9421,
            "altitude_m": 4.0,
            "gnss_status": "NOT_VERIFIED",
            "position_accuracy_m": None
        },
        "device_id": "G3-SENSOR-999",
        "observation_type": "canopy_height",
        "capture_method": "sensor",
        "processing_status": "raw",
        "measurement": 5.2,
        "unit": "m",
        "accuracy": "NOT_VERIFIED",
        "raw_artifact": "TC-Z03-F02/sensor/log_205.txt",
        "raw_artifact_integrity": {
            "checksum_sha256": "f7254999689ae5b530a0006d0fb6765df0317973504e8c5d1b393bfa5826cf9d",
            "hash_algorithm": "sha256",
            "artifact_type": "sensor_reading"
        },
        "provenance_reference": "TC-Z03-F02/qa/qa_F02.json",
        "provenance": {
            "device_id": "G3-SENSOR-999",
            "mission_id": "TC-Z03-F02",
            "captured_at": "2026-08-26T10:00:00Z",
            "raw_artifact": "TC-Z03-F02/sensor/log_205.txt"
        },
        "idempotency_key": "IK-TC-Z03-F02-SENSOR-OBS205"
    }

    res = client.post("/observations", json=payload)
    assert res.status_code == 201

    retrieved = client.get("/observations/TC-Z03-F02-SENSOR-OBS205")
    assert retrieved.status_code == 200
    data = retrieved.json()["observation"]
    geo = data["geo_location"]

    assert geo is not None
    assert geo["place_name"] == "Group 3 observation location"
    assert geo["place_name"] != data["synthetic_state"]
    assert geo["crs"] == "EPSG:4326"
    assert geo["altitude_m"] == 4.0
    assert geo["latitude"] == 19.1288
    assert geo["longitude"] == 72.9421


def test_v22_persistence_fields_and_source_derivation():
    payload = {
        "contract_version": "2.2",
        "schema_version": "2.2",
        "observation_id": "TC-Z03-F02-SENSOR-OBS301",
        "source_identity": "group3-field-edge",
        "survey_id": "TC",
        "zone_id": "Z03",
        "flight_id": "F02",
        "sensor_id": "SENSOR",
        "observation_seq": "OBS301",
        "mission_id": "TC-Z03-F02",
        "observation_timestamp": "2026-08-26T14:00:00Z",
        "source_timestamp": "2026-08-26T14:00:00Z",
        "data_state": "CAPTURED",
        "synthetic_state": "CONTROLLED",
        "is_synthetic": True,
        "calibration_state": "NOT_VERIFIED",
        "quality_state": "CAPTURED",
        "location": {
            "latitude": 19.1288,
            "longitude": 72.9421,
            "altitude_m": 5.0,
            "gnss_status": "NOT_VERIFIED",
            "position_accuracy_m": None
        },
        "device_id": "G3-SENSOR-999",
        "observation_type": "canopy_height",
        "capture_method": "sensor",
        "processing_status": "raw",
        "measurement": 6.1,
        "unit": "m",
        "accuracy": "NOT_VERIFIED",
        "raw_artifact": "TC-Z03-F02/sensor/log_301.txt",
        "raw_artifact_integrity": {
            "checksum_sha256": "f7254999689ae5b530a0006d0fb6765df0317973504e8c5d1b393bfa5826cf9d",
            "hash_algorithm": "sha256",
            "artifact_type": "sensor_reading"
        },
        "provenance_reference": "open-meteo:8d26e68328ac160f",
        "provenance": {
            "device_id": "G3-SENSOR-999",
            "mission_id": "TC-Z03-F02",
            "captured_at": "2026-08-26T14:00:00Z",
            "raw_artifact": "TC-Z03-F02/sensor/log_301.txt"
        },
        "idempotency_key": "IK-TC-Z03-F02-SENSOR-OBS301"
    }

    res = client.post("/observations", json=payload)
    assert res.status_code == 201
    canonical_id_1 = res.json().get("canonical_record_id")
    assert canonical_id_1 is not None

    retrieved = client.get("/observations/TC-Z03-F02-SENSOR-OBS301")
    assert retrieved.status_code == 200
    data = retrieved.json()["observation"]

    assert data["provenance_reference"] == "open-meteo:8d26e68328ac160f"
    assert data["contract_version"] == "2.2"
    assert data["schema_version"] == "2.2"
    assert data["source_timestamp"] == "2026-08-26T14:00:00Z"

    meas = data["measurements"][0]
    prov = meas["provenance"]
    assert prov["source_id"] == "SRC-GROUP3-FIELD-EDGE"
    assert prov["source_id"] != "SRC-GROUP3-SYNTHETIC"
    assert "V2.2" in prov["derivation_note"]
    assert "V2.1" not in prov["derivation_note"]

    # Replay test
    replay_res = client.post("/observations", json=payload)
    assert replay_res.status_code == 200
    assert replay_res.json()["canonical_record_id"] == canonical_id_1

    # Conflict test
    mutated_payload = dict(payload)
    mutated_payload["measurement"] = 99.9
    conflict_res = client.post("/observations", json=mutated_payload)
    assert conflict_res.status_code == 409
    assert conflict_res.json()["canonical_record_id"] is None




def test_v21_field_aliases_and_normalization():
    payload = {
        "observation_id": "TC-Z03-F02-IMX500-OBS202",
        "device_id": "G3-CAM-001",
        "timestamp": "2026-08-19T12:15:00Z",
        "latitude": 19.0500,
        "longitude": 72.9000,
        "quality_state": "RAW",
        "calibration_state": "NOT VERIFIED",
        "accuracy": "NOT VERIFIED",
        "measurement": "mangrove_coverage",
        "raw_artifact_reference": {
            "path": "images/img_202.jpg",
            "artifact_type": "image"
        },
        "processing_status": "qa_passed",
        "provenance": {
            "device_id": "G3-CAM-001",
            "mission_id": "TC-Z03-F02",
            "captured_at": "2026-08-19T12:15:00Z",
            "raw_artifact": "images/img_202.jpg"
        }
    }

    res = client.post("/observations", json=payload)
    assert res.status_code == 201

    retrieved = client.get("/observations/TC-Z03-F02-IMX500-OBS202")
    assert retrieved.status_code == 200
    data = retrieved.json()["observation"]

    assert data["quality_status"] == "RAW"
    assert data["field_observation_meta"]["calibration_status"] == "NOT_VERIFIED"
    assert data["field_observation_meta"]["accuracy_status"] == "NOT_VERIFIED"


def test_v21_image_only_observation_provenance():
    payload = {
        "observation_id": "TC-Z03-F02-IMX500-OBS203",
        "device_id": "G3-CAM-002",
        "timestamp": "2026-08-19T12:30:00Z",
        "latitude": 19.0520,
        "longitude": 72.9020,
        "quality_status": "CAPTURED",
        "calibration_status": "NOT_CALIBRATED",
        "accuracy": "NOT VERIFIED",
        "measurement": None,
        "raw_artifact_reference": {
            "path": "images/img_203.png",
            "artifact_type": "image"
        },
        "processing_status": "raw",
        "provenance": {
            "device_id": "G3-CAM-002",
            "mission_id": "TC-Z03-F02",
            "captured_at": "2026-08-19T12:30:00Z",
            "raw_artifact": "images/img_203.png"
        }
    }

    res = client.post("/observations", json=payload)
    assert res.status_code == 201

    conn = sqlite3.connect(TEST_DB)
    prov = conn.execute("SELECT raw_artifact_id FROM provenance WHERE raw_artifact_id IS NOT NULL").fetchone()
    conn.close()

    assert prov is not None
    assert prov[0].startswith("ART-")


def test_v21_tidal_state_accepted_but_not_persisted():
    payload = {
        "observation_id": "TC-Z03-F02-LIDAR-OBS204",
        "device_id": "G3-LIDAR-001",
        "timestamp": "2026-08-19T13:00:00Z",
        "latitude": 19.0550,
        "longitude": 72.9050,
        "quality_status": "VALIDATED",
        "calibration_status": "CALIBRATED",
        "accuracy": 0.05,
        "unit": "m",
        "measurement": 3.4,
        "parameter": "canopy_height",
        "raw_artifact_reference": {
            "path": "scans/scan_204.las",
            "artifact_type": "point_cloud"
        },
        "processing_status": "qa_passed",
        "provenance": {
            "device_id": "G3-LIDAR-001",
            "mission_id": "TC-Z03-F02",
            "captured_at": "2026-08-19T13:00:00Z",
            "raw_artifact": "scans/scan_204.las"
        },
        "tidal_state": "rising"
    }

    res = client.post("/observations", json=payload)
    assert res.status_code == 201

    retrieved = client.get("/observations/TC-Z03-F02-LIDAR-OBS204")
    assert retrieved.status_code == 200
    data = retrieved.json()["observation"]

    assert "tidal_state" not in data


def test_v22_synthetic_state_preservation_and_mapping():
    payload = {
        "contract_version": "2.2",
        "schema_version": "2.2",
        "observation_id": "TC-Z03-F02-LIDAR-OBS001",
        "source_identity": "group3-field-edge",
        "survey_id": "TC",
        "zone_id": "Z03",
        "flight_id": "F02",
        "sensor_id": "LIDAR",
        "observation_seq": "OBS001",
        "mission_id": "TC-Z03-F02",
        "observation_timestamp": "2026-08-13T09:14:22Z",
        "source_timestamp": "2026-08-13T09:14:22Z",
        "data_state": "VALIDATED",
        "synthetic_state": "CONTROLLED",
        "is_synthetic": True,
        "calibration_state": "NOT_VERIFIED",
        "quality_state": "VALIDATED",
        "location": {
            "latitude": 19.1288,
            "longitude": 72.9421,
            "altitude_m": 120,
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
        "idempotency_key": "IK-TC-Z03-F02-LIDAR-OBS001",
        "hardware_verified": False
    }

    res = client.post("/observations", json=payload)
    assert res.status_code == 201

    retrieved = client.get("/observations/TC-Z03-F02-LIDAR-OBS001")
    assert retrieved.status_code == 200
    data = retrieved.json()["observation"]

    assert data["synthetic_state"] == "CONTROLLED"
    assert data["is_synthetic"] is True


def test_v22_external_api_ext_valid_ingestion():
    import copy
    payload = {
        "contract_version": "2.2",
        "schema_version": "2.2",
        "observation_id": "TC-Z03-EXT-OPENMETEO-OBS001",
        "source_identity": "group3-field-edge",
        "survey_id": "TC",
        "zone_id": "Z03",
        "flight_id": "EXT",
        "sensor_id": "OPENMETEO",
        "observation_seq": "OBS001",
        "mission_id": "TC-Z03-EXT",
        "observation_timestamp": "2026-08-25T12:00:00Z",
        "source_timestamp": "2026-08-25T12:00:00Z",
        "data_state": "CAPTURED",
        "synthetic_state": "CONTROLLED",
        "is_synthetic": True,
        "calibration_state": "NOT_VERIFIED",
        "quality_state": "CAPTURED",
        "location": {
            "latitude": 19.1288,
            "longitude": 72.9421,
            "altitude_m": None,
            "gnss_status": "NOT_VERIFIED",
            "position_accuracy_m": None
        },
        "device_id": "G3-EXT-OPENMETEO-01",
        "observation_type": "weather_data",
        "capture_method": "external_api",
        "processing_status": "raw",
        "measurement": 28.5,
        "unit": "celsius",
        "accuracy": "NOT_VERIFIED",
        "raw_artifact": "TC-Z03-EXT/external/openmeteo_20260825.json",
        "raw_artifact_integrity": {
            "checksum_sha256": "f7254999689ae5b530a0006d0fb6765df0317973504e8c5d1b393bfa5826cf9d",
            "hash_algorithm": "sha256",
            "artifact_type": "sensor_reading"
        },
        "provenance_reference": "TC-Z03-EXT/qa/qa_EXT.json",
        "provenance": {
            "device_id": "G3-EXT-OPENMETEO-01",
            "mission_id": "TC-Z03-EXT",
            "captured_at": "2026-08-25T12:00:00Z",
            "raw_artifact": "TC-Z03-EXT/external/openmeteo_20260825.json",
            "qa_record": "TC-Z03-EXT/qa/qa_EXT.json"
        },
        "idempotency_key": "IK-TC-Z03-EXT-OPENMETEO-OBS001",
        "hardware_verified": False
    }

    res = client.post("/observations", json=payload, headers={"Idempotency-Key": "IK-TC-Z03-EXT-OPENMETEO-OBS001"})
    assert res.status_code == 201

    retrieved = client.get("/observations/TC-Z03-EXT-OPENMETEO-OBS001")
    assert retrieved.status_code == 200
    data = retrieved.json()["observation"]

    assert data["observation_id"] == "TC-Z03-EXT-OPENMETEO-OBS001"
    assert data["capture_method"] == "external_api"
    assert data["device_id"] == "G3-EXT-OPENMETEO-01"


def test_v22_external_api_negative_cases():
    import copy
    base_payload = {
        "contract_version": "2.2",
        "schema_version": "2.2",
        "observation_id": "TC-Z03-EXT-OPENMETEO-OBS001",
        "source_identity": "group3-field-edge",
        "survey_id": "TC",
        "zone_id": "Z03",
        "flight_id": "EXT",
        "sensor_id": "OPENMETEO",
        "observation_seq": "OBS001",
        "mission_id": "TC-Z03-EXT",
        "observation_timestamp": "2026-08-25T12:00:00Z",
        "data_state": "CAPTURED",
        "synthetic_state": "CONTROLLED",
        "is_synthetic": True,
        "calibration_state": "NOT_VERIFIED",
        "quality_state": "CAPTURED",
        "location": {
            "latitude": 19.1288,
            "longitude": 72.9421
        },
        "device_id": "G3-EXT-OPENMETEO-01",
        "observation_type": "weather_data",
        "capture_method": "external_api",
        "processing_status": "raw",
        "measurement": 28.5,
        "unit": "celsius",
        "accuracy": "NOT_VERIFIED",
        "raw_artifact": "TC-Z03-EXT/external/openmeteo_20260825.json",
        "raw_artifact_integrity": {
            "artifact_type": "sensor_reading"
        },
        "provenance_reference": "TC-Z03-EXT/qa/qa_EXT.json",
        "provenance": {
            "device_id": "G3-EXT-OPENMETEO-01",
            "mission_id": "TC-Z03-EXT",
            "captured_at": "2026-08-25T12:00:00Z",
            "raw_artifact": "TC-Z03-EXT/external/openmeteo_20260825.json"
        },
        "idempotency_key": "IK-TC-Z03-EXT-OPENMETEO-OBS001"
    }

    # 1. external_api + flight_id F001 -> REJECT
    p1 = copy.deepcopy(base_payload)
    p1["observation_id"] = "TC-Z03-F001-OPENMETEO-OBS001"
    p1["flight_id"] = "F001"
    p1["mission_id"] = "TC-Z03-F001"
    p1["provenance"]["mission_id"] = "TC-Z03-F001"
    p1["idempotency_key"] = "IK-TC-Z03-F001-OPENMETEO-OBS001"
    res1 = client.post("/observations", json=p1)
    assert res1.status_code == 400

    # 2. EXT + capture_method sensor -> REJECT
    p2 = copy.deepcopy(base_payload)
    p2["capture_method"] = "sensor"
    res2 = client.post("/observations", json=p2)
    assert res2.status_code == 400

    # 3. EXT + capture_method aerial -> REJECT
    p3 = copy.deepcopy(base_payload)
    p3["capture_method"] = "aerial"
    res3 = client.post("/observations", json=p3)
    assert res3.status_code == 400

    # 4. G3-EXT-* device + capture_method sensor -> REJECT
    p4 = copy.deepcopy(base_payload)
    p4["observation_id"] = "TC-Z03-F02-OPENMETEO-OBS001"
    p4["flight_id"] = "F02"
    p4["mission_id"] = "TC-Z03-F02"
    p4["provenance"]["mission_id"] = "TC-Z03-F02"
    p4["capture_method"] = "sensor"
    p4["idempotency_key"] = "IK-TC-Z03-F02-OPENMETEO-OBS001"
    res4 = client.post("/observations", json=p4)
    assert res4.status_code == 400

    # 5. external_api + synthetic_state PHYSICAL -> REJECT
    p5 = copy.deepcopy(base_payload)
    p5["synthetic_state"] = "PHYSICAL"
    p5["is_synthetic"] = False
    p5["hardware_verified"] = True
    p5["raw_artifact_integrity"]["checksum_sha256"] = "a" * 64
    p5["raw_artifact_integrity"]["hash_algorithm"] = "sha256"
    res5 = client.post("/observations", json=p5)
    assert res5.status_code == 400

    # 6. Invalid observation_id pattern -> REJECT
    p6 = copy.deepcopy(base_payload)
    p6["observation_id"] = "INVALID-OBS-ID"
    res6 = client.post("/observations", json=p6)
    assert res6.status_code == 400

    # 7. Invalid flight_id pattern -> REJECT
    p7 = copy.deepcopy(base_payload)
    p7["flight_id"] = "EXT123"
    res7 = client.post("/observations", json=p7)
    assert res7.status_code == 400


def test_canonical_record_id_is_returned_on_ingest_and_get():
    observation = load_observations()[0].copy()
    observation["observation_id"] = "TC-Z03-F02-LIDAR-OBS077"
    observation["observation_seq"] = "OBS077"
    observation["idempotency_key"] = "IK-TC-Z03-F02-LIDAR-OBS077"

    res = client.post("/observations", json=observation)
    assert res.status_code == 201
    body = res.json()
    assert body["status"] == "ACCEPTED"
    canonical_id = body.get("canonical_record_id")
    assert canonical_id is not None
    assert canonical_id.startswith("CR-")

    retrieved = client.get("/observations/TC-Z03-F02-LIDAR-OBS077")
    assert retrieved.status_code == 200
    ret_body = retrieved.json()
    assert ret_body["status"] == "RETRIEVED"
    assert ret_body["observation"]["canonical_record_id"] == canonical_id


def test_canonical_record_id_preserved_on_idempotent_replay():
    observation = load_observations()[0].copy()
    observation["observation_id"] = "TC-Z03-F02-LIDAR-OBS078"
    observation["observation_seq"] = "OBS078"
    observation["idempotency_key"] = "IK-TC-Z03-F02-LIDAR-OBS078"
    headers = {"Idempotency-Key": "IK-TC-Z03-F02-LIDAR-OBS078"}

    res1 = client.post("/observations", json=observation, headers=headers)
    assert res1.status_code == 201
    canonical_id_1 = res1.json().get("canonical_record_id")
    assert canonical_id_1 is not None and canonical_id_1.startswith("CR-")

    res2 = client.post("/observations", json=observation, headers=headers)
    assert res2.status_code == 200
    assert res2.json()["status"] == "IDEMPOTENT_REPLAY"
    assert res2.json().get("canonical_record_id") == canonical_id_1


def test_canonical_record_id_is_none_on_409_conflict():
    observation = load_observations()[0].copy()
    observation["observation_id"] = "TC-Z03-F02-LIDAR-OBS079"
    observation["observation_seq"] = "OBS079"
    observation["idempotency_key"] = "IK-TC-Z03-F02-LIDAR-OBS079"
    headers = {"Idempotency-Key": "IK-TC-Z03-F02-LIDAR-OBS079"}

    res1 = client.post("/observations", json=observation, headers=headers)
    assert res1.status_code == 201

    mutated = observation.copy()
    mutated["observation_type"] = "MUTATED_TYPE"
    res2 = client.post("/observations", json=mutated, headers=headers)
    assert res2.status_code == 409
    assert res2.json()["status"] == "IDEMPOTENCY_CONFLICT"
    assert res2.json().get("canonical_record_id") is None


def test_source_type_external_api_is_accepted():
    payload = {
        "contract_version": "2.2",
        "schema_version": "2.2",
        "observation_id": "MU-Z01-EXT-OPENMETEO-OBS001",
        "source_identity": "group1-compat-layer",
        "survey_id": "MU",
        "zone_id": "Z01",
        "flight_id": "EXT",
        "sensor_id": "OPENMETEO",
        "observation_seq": "OBS001",
        "mission_id": "MU-Z01-EXT",
        "observation_timestamp": "2026-08-28T10:00:00Z",
        "source_timestamp": "2026-08-28T10:00:00Z",
        "data_state": "CAPTURED",
        "synthetic_state": "CONTROLLED",
        "is_synthetic": True,
        "calibration_state": "NOT_VERIFIED",
        "quality_state": "CAPTURED",
        "location": {
            "latitude": 19.0500,
            "longitude": 72.8700,
            "altitude_m": None,
            "gnss_status": "NOT_VERIFIED",
            "position_accuracy_m": None,
        },
        "device_id": "G3-EXT-OPENMETEO-01",
        "observation_type": "weather_data",
        "capture_method": "external_api",
        "processing_status": "raw",
        "measurement": 29.1,
        "unit": "celsius",
        "accuracy": "NOT_VERIFIED",
        "raw_artifact": "MU-Z01-EXT/external/openmeteo_20260828.json",
        "raw_artifact_integrity": {
            "checksum_sha256": "a" * 64,
            "hash_algorithm": "sha256",
            "artifact_type": "sensor_reading",
        },
        "provenance_reference": "MU-Z01-EXT/qa/qa_EXT.json",
        "provenance": {
            "device_id": "G3-EXT-OPENMETEO-01",
            "mission_id": "MU-Z01-EXT",
            "captured_at": "2026-08-28T10:00:00Z",
            "raw_artifact": "MU-Z01-EXT/external/openmeteo_20260828.json",
            "qa_record": "MU-Z01-EXT/qa/qa_EXT.json",
        },
        "idempotency_key": "IK-MU-Z01-EXT-OPENMETEO-OBS001",
        "hardware_verified": False,
    }

    res = client.post(
        "/observations",
        json=payload,
        headers={"Idempotency-Key": "IK-MU-Z01-EXT-OPENMETEO-OBS001"},
    )
    assert res.status_code == 201
    assert res.json()["status"] == "ACCEPTED"
    assert res.json()["observation_id"] == "MU-Z01-EXT-OPENMETEO-OBS001"

    retrieved = client.get("/observations/MU-Z01-EXT-OPENMETEO-OBS001")
    assert retrieved.status_code == 200
    data = retrieved.json()["observation"]
    assert data["capture_method"] == "external_api"

    conn = sqlite3.connect(str(TEST_DB))
    row = conn.execute(
        "SELECT source_type FROM source WHERE source_id = ?",
        ("SRC-GROUP1-COMPAT-LAYER",),
    ).fetchone()
    conn.close()
    assert row is not None
    assert row[0] == "EXTERNAL_API"


def test_source_type_group3_field_capture_is_accepted():
    payload = {
        "contract_version": "2.2",
        "schema_version": "2.2",
        "observation_id": "TC-Z03-F02-LIDAR-OBS100",
        "source_identity": "group3-field-edge",
        "survey_id": "TC",
        "zone_id": "Z03",
        "flight_id": "F02",
        "sensor_id": "LIDAR",
        "observation_seq": "OBS100",
        "mission_id": "TC-Z03-F02",
        "observation_timestamp": "2026-08-28T11:00:00Z",
        "source_timestamp": "2026-08-28T11:00:00Z",
        "data_state": "CAPTURED",
        "synthetic_state": "UNKNOWN",
        "is_synthetic": None,
        "calibration_state": "NOT_VERIFIED",
        "quality_state": "CAPTURED",
        "location": {
            "latitude": 19.1288,
            "longitude": 72.9421,
            "altitude_m": 120,
            "gnss_status": "NOT_VERIFIED",
            "position_accuracy_m": None,
        },
        "device_id": "G3-LIDAR-001",
        "observation_type": "canopy_height",
        "capture_method": "aerial",
        "processing_status": "raw",
        "measurement": 5.2,
        "unit": "m",
        "accuracy": "NOT_VERIFIED",
        "raw_artifact": "TC-Z03-F02/drone/pointcloud_F02_100.las",
        "raw_artifact_integrity": {
            "checksum_sha256": "b" * 64,
            "hash_algorithm": "sha256",
            "artifact_type": "point_cloud",
        },
        "provenance_reference": "TC-Z03-F02/qa/qa_F02.json",
        "provenance": {
            "device_id": "G3-LIDAR-001",
            "mission_id": "TC-Z03-F02",
            "captured_at": "2026-08-28T11:00:00Z",
            "raw_artifact": "TC-Z03-F02/drone/pointcloud_F02_100.las",
            "operator": "<field operator>",
            "qa_record": "TC-Z03-F02/qa/qa_F02.json",
        },
        "idempotency_key": "IK-TC-Z03-F02-LIDAR-OBS100",
        "hardware_verified": False,
    }

    res = client.post(
        "/observations",
        json=payload,
        headers={"Idempotency-Key": "IK-TC-Z03-F02-LIDAR-OBS100"},
    )
    assert res.status_code == 201
    assert res.json()["status"] == "ACCEPTED"
    assert res.json()["observation_id"] == "TC-Z03-F02-LIDAR-OBS100"

    retrieved = client.get("/observations/TC-Z03-F02-LIDAR-OBS100")
    assert retrieved.status_code == 200
    data = retrieved.json()["observation"]
    assert data["capture_method"] == "aerial"

    conn = sqlite3.connect(str(TEST_DB))
    row = conn.execute(
        "SELECT source_type FROM source WHERE source_id = ?",
        ("SRC-GROUP3-FIELD-EDGE",),
    ).fetchone()
    conn.close()
    assert row is not None
    assert row[0] == "GROUP3_FIELD_CAPTURE"


def test_v22_external_api_new_dataset_creation():
    payload = {
        "contract_version": "2.2",
        "schema_version": "2.2",
        "observation_id": "MU-Z01-EXT-OPENMETEO-OBS001",
        "source_identity": "group3-field-edge-mumbai",
        "survey_id": "MU",
        "zone_id": "Z01",
        "flight_id": "EXT",
        "sensor_id": "OPENMETEO",
        "observation_seq": "OBS001",
        "mission_id": "MU-Z01-EXT",
        "observation_timestamp": "2026-08-29T07:11:16Z",
        "source_timestamp": "2026-08-29T07:11:16Z",
        "data_state": "CAPTURED",
        "synthetic_state": "CONTROLLED",
        "is_synthetic": True,
        "calibration_state": "NOT_VERIFIED",
        "quality_state": "CAPTURED",
        "location": {
            "latitude": 19.0430,
            "longitude": 72.8530,
            "altitude_m": 4.0,
            "gnss_status": "NOT_VERIFIED",
            "position_accuracy_m": None,
        },
        "device_id": "G3-EXT-OPENMETEO-01",
        "observation_type": "precipitation",
        "capture_method": "external_api",
        "processing_status": "raw",
        "measurement": 0.1,
        "unit": "mm",
        "accuracy": "NOT_VERIFIED",
        "raw_artifact": "MU-Z01-EXT/openmeteo.json",
        "raw_artifact_integrity": {
            "checksum_sha256": "8d26e68328ac160f7b69f1a24ccb2de4972ff9fc60af11093c246903a7c52502",
            "hash_algorithm": "sha256",
            "artifact_type": "sensor_reading",
        },
        "provenance_reference": "open-meteo:test",
        "provenance": {
            "device_id": "G3-EXT-OPENMETEO-01",
            "mission_id": "MU-Z01-EXT",
            "captured_at": "2026-08-29T07:11:16Z",
            "raw_artifact": "MU-Z01-EXT/openmeteo.json",
        },
        "idempotency_key": "IK-MU-Z01-EXT-OPENMETEO-OBS001",
        "hardware_verified": False,
    }

    response = client.post(
        "/observations",
        json=payload,
        headers={"Idempotency-Key": payload["idempotency_key"]},
    )

    assert response.status_code == 201, response.text

    retrieved = client.get("/observations/MU-Z01-EXT-OPENMETEO-OBS001")
    assert retrieved.status_code == 200, retrieved.text


def test_v22_new_dataset_uses_masterdb_schema_version():
    payload = {
        "contract_version": "2.2",
        "schema_version": "2.2",
        "observation_id": "MU-Z01-EXT-OPENMETEO-OBS901",
        "source_identity": "open-meteo-mumbai-test",
        "survey_id": "MU",
        "zone_id": "Z01",
        "sensor_id": "OPENMETEO",
        "observation_seq": "OBS901",
        "mission_id": "MU-Z01",
        "observation_timestamp": "2026-08-29T10:00:00Z",
        "source_timestamp": "2026-08-29T10:00:00Z",
        "data_state": "CAPTURED",
        "synthetic_state": "CONTROLLED",
        "is_synthetic": True,
        "calibration_state": "NOT_VERIFIED",
        "quality_state": "CAPTURED",
        "location": {
            "latitude": 19.0430,
            "longitude": 72.8530,
            "altitude_m": 4.0,
            "gnss_status": "NOT_VERIFIED",
            "position_accuracy_m": None
        },
        "device_id": "G3-EXT-OPENMETEO-01",
        "observation_type": "temperature",
        "capture_method": "external_api",
        "processing_status": "raw",
        "measurement": 30.0,
        "unit": "C",
        "accuracy": "NOT_VERIFIED",
        "raw_artifact": "MU-Z01-EXT-OPENMETEO/test.json",
        "raw_artifact_integrity": {
            "checksum_sha256": "f7254999689ae5b530a0006d0fb6765df0317973504e8c5d1b393bfa5826cf9d",
            "hash_algorithm": "sha256",
            "artifact_type": "other"
        },
        "provenance_reference": "open-meteo:test",
        "provenance": {
            "device_id": "G3-EXT-OPENMETEO-01",
            "mission_id": "MU-Z01",
            "captured_at": "2026-08-29T10:00:00Z",
            "raw_artifact": "MU-Z01-EXT-OPENMETEO/test.json"
        },
        "hardware_verified": False,
        "idempotency_key": "IK-MU-Z01-EXT-OPENMETEO-OBS901"
    }

    res = client.post("/observations", json=payload)

    print("DEBUG RESPONSE:", res.status_code, res.text)
    assert res.status_code == 201
    canonical_id = res.json()["canonical_record_id"]
    assert canonical_id.startswith("CR-")

    retrieved = client.get(
        "/observations/MU-Z01-EXT-OPENMETEO-OBS901"
    )

    assert retrieved.status_code == 200

    data = retrieved.json()["observation"]

    assert data["contract_version"] == "2.2"
    assert data["schema_version"] == "2.2"

    conn = sqlite3.connect(TEST_DB)

    row = conn.execute(
        """
        SELECT d.schema_version
        FROM dataset d
        JOIN observation o
          ON o.dataset_id = d.dataset_id
        WHERE o.observation_id = ?
        """,
        ("MU-Z01-EXT-OPENMETEO-OBS901",),
    ).fetchone()

    conn.close()

    assert row is not None
    assert row[0] == "0.9.3"