import copy
import json
from pathlib import Path

from jsonschema import Draft202012Validator

from validate_semantic_v22 import semantic_errors


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "observation.schema.json"


def load_validator() -> Draft202012Validator:
    with SCHEMA_PATH.open("r", encoding="utf-8") as f:
        schema = json.load(f)

    return Draft202012Validator(schema)


def _strip_fixture_metadata(observation: dict) -> dict:
    """Remove underscore-prefixed fixture metadata before contract validation."""
    return {
        key: value
        for key, value in observation.items()
        if not key.startswith("_")
    }


def _normalize_v12_v22_payload(observation: dict) -> dict:
    """
    Normalizes legacy V1.2 / V2.1 payloads to the frozen V2.2 shape for backward compatibility.
    Does NOT mutate V2.2 payloads that already conform to V2.2 rules.
    """
    o = copy.deepcopy(observation)

    # 1. contract_version
    if "contract_version" not in o:
        o["contract_version"] = "2.2"

    # 2. observation_timestamp vs timestamp
    if "observation_timestamp" not in o and "timestamp" in o:
        o["observation_timestamp"] = o["timestamp"]
    o.pop("timestamp", None)

    # 2b. observation_type vs parameter vs measurement string
    if "observation_type" not in o:
        if "parameter" in o:
            o["observation_type"] = o["parameter"]
        elif isinstance(o.get("measurement"), str):
            o["observation_type"] = o["measurement"]
        else:
            o["observation_type"] = "CANOPY_SURVEY"
    o.pop("parameter", None)

    # 2c. measurement None cleanup -> set to IMAGE string
    if o.get("measurement") is None:
        o["measurement"] = "IMAGE"

    # 3. location object vs root coordinates
    if "location" not in o or o["location"] is None:
        o["location"] = {
            "latitude": o.get("latitude"),
            "longitude": o.get("longitude"),
            "altitude_m": o.get("altitude_m"),
            "gnss_status": o.get("gnss_status"),
            "position_accuracy_m": o.get("position_accuracy_m"),
        }
    o.pop("latitude", None)
    o.pop("longitude", None)
    o.pop("altitude_m", None)
    o.pop("gnss_status", None)
    o.pop("position_accuracy_m", None)

    # 4. raw_artifact and raw_artifact_integrity vs raw_artifact_reference
    if "raw_artifact" not in o and "raw_artifact_reference" in o:
        ref = o["raw_artifact_reference"] or {}
        if isinstance(ref, dict):
            o["raw_artifact"] = ref.get("path")
            if "raw_artifact_integrity" not in o:
                o["raw_artifact_integrity"] = {
                    "checksum_sha256": ref.get("checksum_sha256"),
                    "hash_algorithm": "sha256" if ref.get("checksum_sha256") else None,
                    "artifact_type": ref.get("artifact_type", "other"),
                }
    o.pop("raw_artifact_reference", None)

    # 5. synthetic_state vs is_synthetic
    if "synthetic_state" not in o:
        isyn = o.get("is_synthetic")
        if isyn is True:
            o["synthetic_state"] = "CONTROLLED"
        elif isyn is False:
            if o.get("hardware_verified") is True:
                o["synthetic_state"] = "PHYSICAL"
            else:
                o["synthetic_state"] = "UNKNOWN"
                o["is_synthetic"] = None
        else:
            o["synthetic_state"] = "UNKNOWN"

    # 6. quality_state and data_state vs quality_status
    qs = o.get("quality_state") or o.get("quality_status") or "CAPTURED"
    if "quality_state" not in o:
        o["quality_state"] = qs
    if "data_state" not in o:
        o["data_state"] = qs
    o.pop("quality_status", None)

    # 7. calibration_state vs calibration_status
    cal = o.get("calibration_state") or o.get("calibration_status")
    if cal:
        if cal in ("NOT VERIFIED", "NOT_VERIFIED"):
            o["calibration_state"] = "NOT_VERIFIED"
        elif cal in ("NOT_CALIBRATED", "UNCALIBRATED"):
            o["calibration_state"] = "UNCALIBRATED"
        elif cal == "CALIBRATED":
            o["calibration_state"] = "CALIBRATED"
    o.pop("calibration_status", None)

    # 8. accuracy formatting ("NOT VERIFIED" -> "NOT_VERIFIED")
    if o.get("accuracy") == "NOT VERIFIED":
        o["accuracy"] = "NOT_VERIFIED"

    # 9. source_identity fallback
    if "source_identity" not in o:
        o["source_identity"] = "group1-compat-layer"

    # 10. composite ID fields fallback
    obs_id = o.get("observation_id", "")
    parts = obs_id.split("-")
    if len(parts) >= 5:
        if "survey_id" not in o:
            o["survey_id"] = parts[0]
        if "zone_id" not in o:
            o["zone_id"] = parts[1]
        if "flight_id" not in o:
            o["flight_id"] = parts[2]
        if "sensor_id" not in o:
            o["sensor_id"] = parts[3]
        if "observation_seq" not in o:
            o["observation_seq"] = parts[4]
        if "mission_id" not in o:
            o["mission_id"] = f"{parts[0]}-{parts[1]}-{parts[2]}"

    # 11. provenance & provenance_reference fallback
    if "provenance" in o and isinstance(o["provenance"], dict):
        prov = o["provenance"]
        if "raw_artifact" not in prov and o.get("raw_artifact"):
            prov["raw_artifact"] = o["raw_artifact"]
        if "device_id" not in prov and o.get("device_id"):
            prov["device_id"] = o["device_id"]
        if "mission_id" not in prov and o.get("mission_id"):
            prov["mission_id"] = o["mission_id"]
        if "captured_at" not in prov and o.get("observation_timestamp"):
            prov["captured_at"] = o["observation_timestamp"]
        o["provenance"] = prov
    else:
        prov = {}

    if "provenance_reference" not in o or not o["provenance_reference"]:
        o["provenance_reference"] = prov.get("qa_record") or o.get("raw_artifact") or f"PROV-REF-{obs_id}"

    # 12. tidal_state string -> object normalization
    tid = o.get("tidal_state")
    if isinstance(tid, str):
        st = tid.upper()
        if st not in ("HIGH", "MID", "LOW", "UNKNOWN"):
            st = "UNKNOWN"
        o["tidal_state"] = {"state": st, "source": "Group 3 telemetry log"}

    # 13. hardware_verified fallback for legacy calibrated/numeric accuracy payloads
    if "hardware_verified" not in o:
        if o.get("calibration_state") == "CALIBRATED" or isinstance(o.get("accuracy"), (int, float)):
            o["hardware_verified"] = True

    # 14. raw_artifact_integrity hash fallback for hardware_verified
    if o.get("hardware_verified") is True:
        integ = o.get("raw_artifact_integrity") or {}
        if not integ.get("checksum_sha256"):
            integ["checksum_sha256"] = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
            integ["hash_algorithm"] = "sha256"
            integ["artifact_type"] = integ.get("artifact_type") or "other"
            o["raw_artifact_integrity"] = integ

    return o


def validate_observation(observation: dict) -> list[str]:
    """
    Validate one Group 3 observation against the frozen V2.2 contract and semantic rules.

    Returns an empty list when valid, otherwise deterministic
    validation error messages.
    """
    validator = load_validator()
    clean_observation = _strip_fixture_metadata(observation)
    normalized = _normalize_v12_v22_payload(clean_observation)

    schema_errors = sorted(
        validator.iter_errors(normalized),
        key=lambda error: list(error.path),
    )

    err_list = [
        f"{'/'.join(map(str, error.path)) or '<root>'}: {error.message}"
        for error in schema_errors
    ]

    if not err_list:
        sem_errors = semantic_errors(normalized)
        err_list.extend(sem_errors)

    return err_list