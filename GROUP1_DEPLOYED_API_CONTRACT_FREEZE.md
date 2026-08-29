# GROUP 1 DEPLOYED API CONTRACT FREEZE

**Date:** 2026-08-29  
**Status:** **FROZEN / PRODUCTION-AGREED**  
**API Version:** `0.1.1` (Canonical VANA Data Foundation)  
**Schema Version:** `0.4`  
**Author:** Group 1 Canonical Observation / Runtime Verification Engineer  

---

## 1. Endpoints & Network Topology

### 1.1 Ingestion Endpoint
- **HTTP Method:** `POST`
- **Path:** `/ingest/observations` (and `/observations`)
- **Authentication:** None / Internal VPC Service-to-Service
- **Request Headers:**
  - `Content-Type: application/json` (Required)
  - `Idempotency-Key: <string>` (Optional, highly recommended for guaranteed `0 → 1 → 1` replay)

### 1.2 Retrieval Endpoint
- **HTTP Method:** `GET`
- **Path:** `/observations/{observation_id}` (and `/ingest/observations/{observation_id}`)
- **Path Parameters:**
  - `observation_id` (string, required): The caller-supplied observation primary key.
- **Request Headers:**
  - `Accept: application/json`

### 1.3 Health Endpoint
- **HTTP Method:** `GET`
- **Path:** `/health`
- **Response:** `{"status": "healthy", "service": "VANA Integrity Ingestion", "version": "0.1.1"}`

---

## 2. Ingestion Request Contract (`POST /ingest/observations`)

### Request Field Specification:

| Field | Required | Type | Validation / Constraints | Meaning | Source |
|---|---|---|---|---|---|
| `observation_id` | **YES** | String | Non-empty, caller-supplied unique identity | Primary logical observation key | Group 3 Edge |
| `source` | **YES** | Object | Must contain valid fields below | Metadata describing the origin authority | Group 3 Edge |
| `source.source_id` | **YES** | String | Non-empty | Unique identifier for data source | Group 3 / MasterDB |
| `source.source_type` | **YES** | String | Enum: `SCIENTIFIC_LITERATURE`, `GOVERNMENT_DATASET`, `EARTH_OBSERVATION`, `INSTITUTIONAL`, `SYNTHETIC_TEST`, `GROUP3_FIELD_CAPTURE` | Category of data capture | Group 3 Edge |
| `source.title` | **YES** | String | Non-empty | Descriptive title of data source | Group 3 Edge |
| `source.is_synthetic` | **YES** | Boolean | Required `True` if `source_type == 'SYNTHETIC_TEST'`, `False` for physical captures | Synthetic vs physical flag | Group 3 Edge |
| `source.publisher` | NO | String | Nullable | Publishing institution/agency | Group 3 Edge |
| `source.url` | NO | String | Nullable | Source reference URL | Group 3 Edge |
| `source.citation` | NO | String | Nullable | Formal academic/agency citation | Group 3 Edge |
| `source.notes` | NO | String | Nullable | Free-form explanatory notes | Group 3 Edge |
| `dataset` | **YES** | Object | Must contain valid fields below | Mission/survey grouping batch | Group 3 Edge |
| `dataset.dataset_id` | **YES** | String | Non-empty | Unique dataset/mission grouping key | Group 3 Edge |
| `dataset.dataset_name` | **YES** | String | Non-empty | Descriptive dataset title | Group 3 Edge |
| `dataset.schema_version`| **YES** | String | Must be registered: `"0.3"` or `"0.4"` | Canonical schema version reference | Group 1 Registry |
| `dataset.methodology` | NO | String | Nullable | Scientific methodology description | Group 3 Edge |
| `geo_location` | NO | Object | Point coordinates block | Geographic coordinate representation | Group 3 GPS/GNSS |
| `geo_location.geo_id` | NO | String | Auto-generated if omitted: `GEO-<obs_id>` | Geography record identifier | Group 1 / Group 3 |
| `geo_location.scope` | NO | String | Default: `'POINT'` (Enum: `'POINT'`, `'ZONE'`) | Geography spatial scope | Group 1 Standard |
| `geo_location.place_name`| NO | String | Non-empty string | Human readable location name | Group 3 / Surveyor |
| `geo_location.lat` | NO | Float | WGS84 Latitude ($-90.0$ to $+90.0$) | GPS Latitude | Group 3 Sensor |
| `geo_location.lon` | NO | Float | WGS84 Longitude ($-180.0$ to $+180.0$) | GPS Longitude | Group 3 Sensor |
| `geo_location.crs` | NO | String | Default: `'EPSG:4326'` | Coordinate reference system | Group 1 Standard |
| `observation` | **YES** | Object | Core observation attributes | Primary observation metadata | Group 3 Edge |
| `observation.observation_type` | **YES** | String | Non-empty (e.g. `'CARBON_STOCK'`, `'BIOMASS'`) | What parameter was measured | Group 3 Edge |
| `observation.observed_at` | NO | String | ISO-8601 UTC Timestamp (`YYYY-MM-DDTHH:MM:SSZ`) | Moment of physical observation | Group 3 Sensor |
| `observation.capture_method` | NO | String | Enum: `'aerial'`, `'ground'`, `'sensor'`, `'site_evidence'` | Physical method of data capture | Group 3 Edge |
| `observation.species` | NO | String | Nullable | Biological taxonomy name | Group 3 Edge |
| `observation.confidence` | NO | String | Enum: `'HIGH'`, `'MEDIUM'`, `'LOW'`, `'UNCERTAIN'` | Assessment confidence | Group 3 QA |
| `field_observation_meta`| NO | Object | Field sensor metadata | Hardware / execution telemetry | Group 3 Drone/Sensor |
| `field_observation_meta.device_id` | NO | String | Nullable | Hardware serial / device ID | Group 3 Hardware |
| `field_observation_meta.operator` | NO | String | Nullable | Field crew operator identifier | Group 3 Field Team |
| `field_observation_meta.mission_id` | NO | String | Nullable | Survey flight / mission ID | Group 3 Mission |
| `field_observation_meta.accuracy` | NO | Float | Nullable (never invent a value) | Sensor measurement accuracy | Group 3 Calibration |
| `field_observation_meta.calibration_status` | NO | String | Enum: `'CALIBRATED'`, `'UNCALIBRATED'`, `'NOT_VERIFIED'` | Sensor calibration state | Group 3 QA |
| `measurements` | **YES** | Array | Non-empty list of measurement objects | Quantitative measurement readings | Group 3 Sensor |
| `measurements[].metric_name` | **YES** | String | Non-empty string | Name of metric measured | Group 3 Sensor |
| `measurements[].data_type` | NO | String | Default: `'NUMERIC'` (Enum: `'NUMERIC'`, `'TEXT'`, `'BOOLEAN'`) | Data representation type | Group 3 Sensor |
| `measurements[].value` | Conditional | Float | Required if `data_type == 'NUMERIC'` | Numerical reading | Group 3 Sensor |
| `measurements[].value_text` | Conditional | String | Required if `data_type in ('TEXT','BOOLEAN')` | Categorical / text reading | Group 3 Sensor |
| `measurements[].unit` | NO | String | Measurement unit (e.g. `'Mg/ha'`, `'m'`) | Physical unit of measure | Group 3 Sensor |
| `raw_artifact` | **YES** | Object | Evidence artifact pointer | Raw LiDAR, image, sensor file ref | Group 3 Pipeline |
| `raw_artifact.content` | Conditional | String | Content or string representation of raw bytes | Raw payload content | Group 3 Pipeline |
| `raw_artifact.ref` | **YES** | String | Durable URI / file path pointer | Storage location pointer | Group 3 Storage |
| `processing` | **YES** | Object | Pipeline execution run context | Pipeline stage audit trail | Group 1 / Group 3 |
| `processing.pipeline_stage`| NO | String | Default: `'INGEST'` (Enum: `EXTRACT`, `NORMALISE`, `VALIDATE`, `PROVENANCE`, `INGEST`) | Pipeline lifecycle stage | Ingestion Engine |
| `processing.actor` | **YES** | String | Non-empty string | Agent or system executing stage | Ingestion Engine |
| `provenance` | **YES** | Object | Lineage derivation block | Audit trail explanation | Group 1 / Group 3 |
| `provenance.derivation_note`| **YES** | String | Non-empty explanation of derivation | Human/system readable audit note| Group 3 / Analyst |

---

## 3. Response Contract

### 3.1 Ingestion Response (`POST /ingest/observations`)

#### First-Time Creation (`HTTP 201 Created`):
```json
{
  "status": "ok",
  "observation_id": "TC-MB-Z01-F01-LIDAR-OBS001",
  "idempotent": false,
  "run_id": "RUN-7a1b2c3d4e5f",
  "input_ref": "sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855@fixtures/regions/mb_z01.json"
}
```

#### Idempotent Replay (`HTTP 200 OK`):
```json
{
  "status": "ok",
  "observation_id": "TC-MB-Z01-F01-LIDAR-OBS001",
  "idempotent": true
}
```

### 3.2 Retrieval Response (`GET /observations/{observation_id}`)

#### Success (`HTTP 200 OK`):
```json
{
  "status": "ok",
  "observation": {
    "observation_id": "TC-MB-Z01-F01-LIDAR-OBS001",
    "canonical_record_id": "TC-MB-Z01-F01-LIDAR-OBS001",
    "dataset": {
      "dataset_id": "DS-MB-MUMBAI-CARBON-001",
      "dataset_name": "VANA Regional Carbon Dataset - Mumbai",
      "schema_version": "0.4",
      "source_id": "SRC-MB-MUMBAI-001"
    },
    "source": {
      "source_id": "SRC-MB-MUMBAI-001",
      "source_type": "GROUP3_FIELD_CAPTURE",
      "title": "VANA Field Survey - Mumbai",
      "is_synthetic": false
    },
    "observation": {
      "observation_id": "TC-MB-Z01-F01-LIDAR-OBS001",
      "observed_at": "2026-08-29T10:00:00Z",
      "capture_method": "aerial",
      "species": "Avicennia marina",
      "observation_type": "CARBON_STOCK",
      "quality_status": "CAPTURED",
      "confidence": "HIGH",
      "created_at": "2026-08-29 11:02:26"
    },
    "geo_location": {
      "geo_id": "GEO-MB-Z01",
      "scope": "POINT",
      "place_name": "Mahim Mangrove Zone, Mumbai, Maharashtra",
      "lat": 19.0435,
      "lon": 72.8423,
      "crs": "EPSG:4326",
      "notes": "High precision GPS coordinate for Mumbai"
    },
    "field_observation_meta": {
      "device_id": "G3-LIDAR-MB-01",
      "operator": "VANA-Field-Operator-01",
      "mission_id": "MISSION-MB-Z01",
      "accuracy": 0.05,
      "accuracy_unit": "m",
      "calibration_status": "CALIBRATED",
      "processing_status": "PROCESSED",
      "notes": "Field verification in Mumbai"
    },
    "measurements": [
      {
        "measurement_id": "MSR-4b92c10aef53",
        "metric_name": "above_ground_biomass",
        "data_type": "NUMERIC",
        "value": 115.4,
        "value_text": null,
        "unit": "Mg/ha",
        "method": "lidar_canopy_model",
        "original_value_text": "115.4 Mg/ha",
        "transform_applied": null,
        "created_at": "2026-08-29 11:02:26"
      }
    ],
    "raw_artifacts": [
      {
        "artifact_id": "ART-91e843c0fa21",
        "artifact_type": "LIDAR_SCAN",
        "storage_ref": "fixtures/regions/mb_z01.json",
        "content_hash": "sha256:7a4f91...fixtures/regions/mb_z01.json",
        "hash_algorithm": "sha256",
        "captured_at": "2026-08-29 11:02:26",
        "notes": "Raw artifact pointer for Mumbai"
      }
    ],
    "provenance": [
      {
        "provenance_id": "PRV-11a22b33c44d",
        "measurement_id": "MSR-4b92c10aef53",
        "source_id": "SRC-MB-MUMBAI-001",
        "run_id": "RUN-7a1b2c3d4e5f",
        "derivation_note": "LiDAR point cloud scan at Mahim Bay mangrove canopy",
        "recorded_at": "2026-08-29 11:02:26"
      }
    ]
  }
}
```

---

## 4. Error Contract Matrix

| Error Scenario | HTTP Status | Response Shape / Detail | Behavior |
|---|---|---|---|
| **Validation Failure (Missing / Invalid Fields)** | `422 Unprocessable Entity` | `{"detail": {"errors": ["caller-supplied observation_id is required", ...]}}` | Full atomic transaction rollback; 0 records stored. |
| **Malformed Identity (Empty / Whitespace)** | `422 Unprocessable Entity` | `{"detail": {"errors": ["caller-supplied observation_id is required"]}}` | Rejection; DB state untouched. |
| **Unregistered Schema Version (`99.0`)** | `422 Unprocessable Entity` | `{"detail": {"errors": ["dataset.schema_version '99.0' is invalid or unregistered"]}}` | Strict schema registry enforcement. |
| **Idempotency Conflict (Same Key, Mutated Payload)** | `409 Conflict` | `{"detail": {"message": "Idempotency-Key '...' was already used with a different request body", "idempotency_key": "..."}}` | Prior record protected; mutation rejected. |
| **Unknown Observation (`GET /observations/{id}`)** | `404 Not Found` | `{"detail": {"message": "Observation '...' not found", "status": "NOT_FOUND"}}` | Standard REST 404 response. |
| **Database / Uncaught Server Error** | `500 Internal Server Error` | `{"detail": "..."}` | Transaction rolled back safely. |
