# VANA MasterDB Observation API Contract

**Version:** 1.0.0  
**Owner:** Group 1 — API / Integration  
**Consumer:** Group 3 field-observation integration

## 1. Purpose

The VANA Observation API provides the consumer-facing boundary for Group 3
field observations.

The API accepts the frozen Group 3 V1.0 observation payload, validates it
against `observation.schema.json`, and provides observation retrieval.

The current implementation uses an in-memory adapter for API contract
verification. Canonical PostgreSQL persistence will be connected after the
approved Group 1 schema/API boundary is available.

## 3. Official historical forest-cover API

FSI ISFR 2023 records use the separate official-data path. They are not
Group 3 observations and do not require device, sensor, flight, calibration,
GNSS, synthetic, or field-capture metadata.

### POST /official/forest-cover

The request contains `source`, `dataset`, `assessment_year`,
`geography_level` (`STATE` or `DISTRICT`), `state`, optional `district` and
`boundary_reference`, the six nullable forest-cover values, optional `unit`
and `methodology`, `quality_status`, required `provenance_reference`, and an
optional `idempotency_key`.

`source.source_type` must be `GOVERNMENT_DATASET`. Numeric values are nullable
when the source extract has not supplied them; the API does not invent them.
District records require `district`; state records require `district: null`.

The first accepted request returns `201`. An identical replay returns `200`
with `status: REPLAY`; a conflicting identity or idempotency key returns
`409` with `status: CONFLICT`.

### GET /official/forest-cover/{record_id}

Returns the official record, assessment year, administrative geography,
forest-cover values, source metadata, and provenance reference. Unavailable
values are returned as `null`.

### GET /datasets/{dataset_id}/forest-cover

Returns `{ "dataset_id": "...", "records": [...] }` for the official
records registered under the dataset.

---

## 2. Endpoints

### GET /health

Checks whether the API is running.

#### Successful response

HTTP `200`

```json
{
  "status": "healthy",
  "service": "VANA MasterDB Observation API",
  "version": "1.0.0"
}