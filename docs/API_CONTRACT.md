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