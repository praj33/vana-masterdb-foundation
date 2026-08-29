# GROUP 1 → GROUP 4 / RAHIL LIVE RUNTIME HANDOFF

**Target Audience:** Rahil / Group 4 Execution Envelope Team  
**Author:** Group 1 Canonical Observation / Runtime Verification Engineer  
**Date:** 2026-08-29  
**Status:** **READY FOR CONSUMPTION / LIVE VERIFIED**  

---

## 1. Quick Integration Guide

Group 4 can immediately consume the Group 1 Data Foundation runtime using either the in-process FastAPI application (`create_app`) or standard HTTP endpoints.

| Requirement | Value / Specification |
|---|---|
| **Base Ingestion Endpoint** | `POST /ingest/observations` (and `POST /observations`) |
| **Base Retrieval Endpoint** | `GET /observations/{observation_id}` (and `GET /ingest/observations/{observation_id}`) |
| **Service Health Check** | `GET /health` |
| **Auth Headers** | None (VPC internal service-to-service) |
| **Idempotency Header** | `Idempotency-Key: <string>` (Send unique observation ID or UUID) |
| **Schema Version** | Set `dataset.schema_version = "0.4"` (or `"0.3"`) |
| **Source Type for Field Ops** | Set `source.source_type = "GROUP3_FIELD_CAPTURE"` with `source.is_synthetic = false` |

---

## 2. Status Categorization of Contract Capabilities

| Capability / Feature | Status | Verification Detail |
|---|---|---|
| **Six-Region Canonical GET** | `VERIFIED LIVE` | All 6 regions (Mumbai, Navi Mumbai, Vasai, Thane, Maval, Alibaug) verified with HTTP 201 POST → HTTP 200 GET. |
| **Idempotency `0 → 1 → 1`** | `VERIFIED LIVE` | Replay with identical key/body returns HTTP 200 `{"idempotent": true}` without creating duplicate rows. |
| **Idempotency Conflict (409)** | `VERIFIED LIVE` | Replay with same key but mutated payload returns HTTP 409 conflict. |
| **Observation Identity Stability** | `VERIFIED LIVE` | Caller-supplied `observation_id` is persisted verbatim as canonical PK (`canonical_record_id`). No `OBS-<hash>` created. |
| **GPS Coordinate Preservation** | `VERIFIED LIVE` | Point latitude, longitude, and place_name stored verbatim in `geo_location`. |
| **Provenance Chain** | `VERIFIED LIVE` | Complete audit trail (`source_id` → `run_id` → `derivation_note`) created and linked to each measurement. |
| **T11 Schema Registry Check** | `VERIFIED LIVE` | Unregistered `schema_version` (e.g. `99.0`) strictly rejected with HTTP 422. |
| **T16 `GROUP3_FIELD_CAPTURE`**| `VERIFIED LIVE` | Accepted as valid physical source type; persisted with `is_synthetic = 0`. |
| **Direct Postgres VM Wiring** | `DOCUMENTED / PENDING ROUTE` | SQLite adapter verified locally; Postgres DDL (`migrations/0001_init.sql`) maintained for VM deployment. |

---

## 3. Mandatory Fields Cheat-Sheet for Group 4

When constructing an observation payload to send to Group 1, ensure these required fields are provided:

```json
{
  "observation_id": "TC-MB-Z01-F01-LIDAR-OBS001",
  "source": {
    "source_id": "SRC-MB-001",
    "source_type": "GROUP3_FIELD_CAPTURE",
    "title": "Field Survey Mumbai",
    "is_synthetic": false
  },
  "dataset": {
    "dataset_id": "DS-MB-001",
    "dataset_name": "Regional Carbon Dataset",
    "schema_version": "0.4"
  },
  "geo_location": {
    "place_name": "Mahim Mangrove Zone",
    "lat": 19.0435,
    "lon": 72.8423
  },
  "observation": {
    "observation_type": "CARBON_STOCK",
    "observed_at": "2026-08-29T10:00:00Z",
    "confidence": "HIGH"
  },
  "measurements": [
    {
      "metric_name": "above_ground_biomass",
      "data_type": "NUMERIC",
      "value": 115.4,
      "unit": "Mg/ha"
    }
  ],
  "raw_artifact": {
    "content": "{\"pointcloud\":\"scan.las\"}",
    "ref": "fixtures/mb_z01.json"
  },
  "processing": {
    "pipeline_stage": "INGEST",
    "actor": "group4-executor"
  },
  "provenance": {
    "derivation_note": "LiDAR point cloud scan"
  }
}
```

---

## 4. Error Handling Protocol for Group 4

1. **HTTP 201 Created:** New observation persisted successfully. Store returned `observation_id` and `run_id`.
2. **HTTP 200 OK (Replay):** Safe idempotent retry; record was already ingested previously.
3. **HTTP 409 Conflict:** Idempotency key reused with different request payload. Group 4 should investigate payload mutation or generate a new unique key.
4. **HTTP 422 Unprocessable Entity:** Payload failed validation (e.g. missing required field, unregistered schema version, malformed ID). Check `detail.errors`.
5. **HTTP 404 Not Found:** Observation ID does not exist in the database when calling `GET /observations/{id}`.

---

## 5. Artifact & Evidence References

- Ingestion Engine: `src/vana_integrity/ingestion.py`
- Validation Engine: `src/vana_integrity/validation.py`
- API Boundary: `src/vana_integrity/api.py`
- Test Script / Verification Harness: `verify_six_regions.py`
- Machine-Readable Evidence: `evidence/group1/six_region_acceptance_summary.json`
