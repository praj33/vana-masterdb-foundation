from typing import Any


def adapt_v21_to_canonical(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Adapt a validated Group 3 V2.1 observation into the
    existing VANA v0.4 persistence input shape.

    Mapping only:
    - preserves observation identity
    - maps approved renamed fields
    - does not invent scientific values
    - does not add tidal_state to the v0.4 canonical model
    """

    location = payload.get("location") or {}
    measurement = payload.get("measurement") or {}
    raw_artifact = payload.get("raw_artifact") or ""
    integrity = payload.get("raw_artifact_integrity") or {}
    provenance = payload.get("provenance") or {}

    return {
        # Identity — preserve exactly.
        "observation_id": payload["observation_id"],

        # V2.1 → v0.4 canonical observation fields.
        "timestamp": payload["timestamp"],
        "observed_at": payload["timestamp"],
        "capture_method": payload.get("capture_method"),
        "observation_type": payload["observation_type"],
        "quality_status": payload["quality_state"],

        # Location.
        "latitude": location.get("latitude"),
        "longitude": location.get("longitude"),

        # Field observation metadata.
        "device_id": payload["device_id"],
        "mission_id": payload["mission_id"],
        "accuracy": payload.get("accuracy"),
        "accuracy_unit": (
            "m"
            if isinstance(payload.get("accuracy"), (int, float))
            else "NOT VERIFIED"
        ),
        "calibration_status": payload["calibration_state"],
        "processing_status": payload.get("processing_status"),

        # V2.1 measurement object.
        "parameter": measurement.get("parameter"),
        "measurement": measurement.get("value"),
        "unit": payload.get("unit"),

        # V2.1 raw artifact is a flat string.
        "raw_artifact_reference": {
            "path": raw_artifact,
            "artifact_type": "point_cloud",
            "checksum_sha256": integrity.get("checksum_sha256"),
        },
        "raw_artifact_sha256": integrity.get("checksum_sha256"),

        # Provenance remains available for the canonical persistence layer.
        "provenance": provenance,

        # V2.1-only context is preserved at the boundary.
        # These values must not silently become v0.4 columns.
        "v21_context": {
            "survey_id": payload.get("survey_id"),
            "zone_id": payload.get("zone_id"),
            "flight_id": payload.get("flight_id"),
            "sensor_id": payload.get("sensor_id"),
            "observation_seq": payload.get("observation_seq"),
            "is_synthetic": payload.get("is_synthetic"),
            "hardware_verified": payload.get("hardware_verified"),
            "waypoint_id": payload.get("waypoint_id"),
            "location": {
                "altitude_m": location.get("altitude_m"),
                "gnss_status": location.get("gnss_status"),
                "position_accuracy_m": location.get(
                    "position_accuracy_m"
                ),
            },
            "measurement_artifact": measurement.get("artifact"),
        },
    }
