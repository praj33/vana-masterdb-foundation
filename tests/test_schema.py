"""v0.4 Schema integration tests (observed_at, geo_location, field_observation_meta, measurements data_types)."""

from __future__ import annotations

import copy
from fastapi.testclient import TestClient


def test_v04_schema_entities_persisted(
    client: TestClient,
    db_conn,
    synthetic_payload: dict,
) -> None:
    payload = copy.deepcopy(synthetic_payload)
    payload["observation_id"] = "TC-Z03-F02-LIDAR-OBS001"
    payload["observation"]["observation_id"] = "TC-Z03-F02-LIDAR-OBS001"
    payload["observation"]["observed_at"] = "2026-08-14T10:30:00Z"
    payload["observation"]["capture_method"] = "LIDAR_SCAN"

    payload["geo_location"] = {
        "geo_id": "GEO-TC-Z03-F02",
        "scope": "POINT",
        "place_name": "Test Plot Alpha",
        "lat": 12.9716,
        "lon": 77.5946,
        "crs": "EPSG:4326",
    }

    payload["field_observation_meta"] = {
        "device_id": "LIDAR-DEV-99",
        "operator": "Operator-01",
        "mission_id": "MISSION-2026-A",
        "accuracy": 0.05,
        "accuracy_unit": "m",
        "calibration_status": "CALIBRATED",
    }

    payload["measurements"] = [
        {
            "metric_name": "biomass",
            "data_type": "NUMERIC",
            "value": 150.2,
            "unit": "Mg/ha",
        },
        {
            "metric_name": "species_label",
            "data_type": "TEXT",
            "value_text": "Tectona grandis",
            "unit": None,
        },
        {
            "metric_name": "canopy_cover_valid",
            "data_type": "BOOLEAN",
            "value_text": "true",
            "unit": None,
        },
    ]

    response = client.post("/ingest/observations", json=payload)
    assert response.status_code == 201
    assert response.json()["observation_id"] == "TC-Z03-F02-LIDAR-OBS001"

    # Verify observation.observed_at & capture_method
    obs_row = db_conn.execute(
        "SELECT observed_at, capture_method FROM observation WHERE observation_id = 'TC-Z03-F02-LIDAR-OBS001'"
    ).fetchone()
    assert obs_row["observed_at"] == "2026-08-14T10:30:00Z"
    assert obs_row["capture_method"] == "LIDAR_SCAN"

    # Verify geo_location scope='POINT'
    geo_row = db_conn.execute(
        "SELECT scope, place_name, lat, lon FROM geo_location WHERE geo_id = 'GEO-TC-Z03-F02'"
    ).fetchone()
    assert geo_row["scope"] == "POINT"
    assert geo_row["place_name"] == "Test Plot Alpha"
    assert abs(geo_row["lat"] - 12.9716) < 1e-4

    # Verify field_observation_meta
    field_row = db_conn.execute(
        "SELECT device_id, operator, calibration_status FROM field_observation_meta WHERE observation_id = 'TC-Z03-F02-LIDAR-OBS001'"
    ).fetchone()
    assert field_row["device_id"] == "LIDAR-DEV-99"
    assert field_row["calibration_status"] == "CALIBRATED"

    # Verify measurements (NUMERIC, TEXT, BOOLEAN)
    m_rows = db_conn.execute(
        "SELECT metric_name, data_type, value, value_text FROM measurement WHERE observation_id = 'TC-Z03-F02-LIDAR-OBS001' ORDER BY metric_name"
    ).fetchall()
    assert len(m_rows) == 3
    m_dict = {r["metric_name"]: r for r in m_rows}
    assert m_dict["biomass"]["data_type"] == "NUMERIC"
    assert abs(m_dict["biomass"]["value"] - 150.2) < 1e-4
    assert m_dict["species_label"]["data_type"] == "TEXT"
    assert m_dict["species_label"]["value_text"] == "Tectona grandis"
    assert m_dict["canopy_cover_valid"]["data_type"] == "BOOLEAN"
    assert m_dict["canopy_cover_valid"]["value_text"] == "true"
