# GROUP 1 FINAL CONTRACT & IDENTITY CHECK
# TC-Z03-EXT-OPENMETEO-OBS001

**Date:** 2026-08-26
**Mode:** READ-ONLY
**Verdict:** CONDITIONAL PASS

---

## 1. Audit Scope

```text
Target:          TC-Z03-EXT-OPENMETEO-OBS001
Contract:        V2.2
Branch:          main (7722fd7)
Mode:            READ-ONLY
Code modified:   NO
DB modified:     NO
POST executed:   NO
Commit:          NO
Push:            NO
```

---

## 2. Authoritative Evidence Sources

| # | Source | File |
|---|--------|------|
| 1 | V2.2 JSON Schema | `observation.schema.v2.2.json` |
| 2 | V2.2 test payload | `tests/test_api.py` — `test_v22_external_api_ext_valid_ingestion()` |
| 3 | API models (Pydantic) | `api/models.py` — `ObservationRequest`, `IngestionResponse`, `RetrievalResponse` |
| 4 | Persistence / retrieval | `api/persistence.py` — GET response construction |
| 5 | DB persistence layer | `vana_db.py` — `insert_observation()`, `check_idempotency_and_ingest()`, `get_observation()` |
| 6 | SQLite schema | `migrations/0001_init_sqlite.sql` |
| 7 | Postgres migration | `migrations/0004_v09_canonical_record_id.sql` |
| 8 | Postgres migration | `migrations/0005_v22_persistence_fields.sql` |
| 9 | Validation | `api/validation.py` — V2.2 normalization and JSON Schema validation |
| 10 | Semantic validation | `validate_semantic_v22.py` — cross-field rules for EXT observations |
| 11 | Acceptance scripts | `eod_rehearsal.py`, `live_acceptance_group1.py` |
| 12 | Sample fixture | `sample_mission_package.v2.2.json` |

---

## 3. Identity Verification

### 3.1 observation_id

```text
Value:   TC-Z03-EXT-OPENMETEO-OBS001
Stable:  YES
```

The `observation_id` is caller-supplied, pattern-validated, and persisted verbatim. Stability is verified across three stages:

| Stage | Evidence |
|-------|----------|
| Request payload | `"observation_id": "TC-Z03-EXT-OPENMETEO-OBS001"` in test fixture |
| Ingestion response | `assert res.status_code == 201` |
| GET retrieval | `assert data["observation_id"] == "TC-Z03-EXT-OPENMETEO-OBS001"` |

The V2.2 schema enforces the observation_id pattern:

```text
^[A-Z0-9]+-Z[0-9]{1,2}-(F[0-9]{1,3}|EXT)-[A-Z0-9]+-OBS[0-9]{3,}$
```

`TC-Z03-EXT-OPENMETEO-OBS001` matches this pattern. The identity module preserves the caller-supplied value without prefix, suffix, or hash transformation.

### 3.2 canonical_record_id

```text
Value:   CR-<uuid> (generated at persistence, never caller-supplied)
Stable:  YES
```

| Behaviour | Evidence |
|-----------|----------|
| Generated on first ingestion | `canonical_record_id = "CR-" + str(uuid.uuid4())` in `vana_db.py` |
| Returned on 201 Created | `canonical_id is not None` asserted in test |
| Stable on GET retrieval | `ret_body["observation"]["canonical_record_id"] == canonical_id` |
| Preserved on 200 idempotent replay | `res2.json().get("canonical_record_id") == canonical_id_1` |
| None on 409 conflict | `res2.json().get("canonical_record_id") is None` |

The `canonical_record_id` is generated once at first persistence, never regenerated on replay, and correctly absent on 409 conflict responses where no new record is created.

---

## 4. Version Verification

| Field | Expected | Actual | Evidence | Result |
|-------|----------|--------|----------|--------|
| `contract_version` | `2.2` | `2.2` | `const: "2.2"` in V2.2 JSON Schema; asserted in tests; defaulted in validation normalizer | **PASS** |
| `schema_version` | `2.2` | `2.2` | Present in test payloads; asserted in retrieval response | **PASS** |

Schema definition:

```json
"contract_version": {
    "type": "string",
    "const": "2.2"
}
```

Validation normalizer:

```python
if "contract_version" not in o:
    o["contract_version"] = "2.2"
```

Retrieval response:

```python
"contract_version": observation[18] if observation[18] is not None else "2.2",
```

---

## 5. Context ID Determination

```text
context_id value:          FIELD DOES NOT EXIST IN THE V2.2 CONTRACT
context_id in response:    ABSENT
Canonical representation:  FIELD OMITTED
```

### Evidence

**1. V2.2 JSON Schema** — The schema declares `"additionalProperties": false` at the root level. The `properties` object defines exactly 34 fields. `context_id` is not among them and is not in the `required` array. Any payload containing `"context_id": null` would be **rejected** by schema validation.

```json
{
  "additionalProperties": false,
  "required": [
    "contract_version", "observation_id", "source_identity",
    "survey_id", "zone_id", "flight_id", "sensor_id",
    "observation_seq", "observation_timestamp", "data_state",
    "synthetic_state", "mission_id", "device_id", "location",
    "observation_type", "measurement", "quality_state",
    "calibration_state", "raw_artifact", "provenance",
    "provenance_reference", "accuracy", "processing_status",
    "raw_artifact_integrity"
  ]
}
```

**2. Pydantic request model** (`api/models.py`) — `ObservationRequest` defines 30+ typed fields. `context_id` is not among them.

**3. Persistence retrieval response** (`api/persistence.py`) — The GET response dictionary enumerates every returned field. `context_id` is not included.

**4. Database schema** (`migrations/0001_init_sqlite.sql`) — The `observation` table contains 18 columns. `context_id` is not among them.

**5. Codebase-wide search** — `context_id` has zero occurrences across all branches:

| Branch | Occurrences |
|--------|-------------|
| `main` | 0 |
| `feature/api-integration` | 0 |
| `feature/schema-foundation` | 0 |
| `feature/integrity-idempotency` | 0 |

**6. TC-Z03-EXT-OPENMETEO-OBS001 test payload** — The authoritative test for this observation does not include `context_id`:

```python
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
    "location": { ... },
    "device_id": "G3-EXT-OPENMETEO-01",
    "observation_type": "weather_data",
    "capture_method": "external_api",
    "processing_status": "raw",
    "measurement": 28.5,
    "unit": "celsius",
    "accuracy": "NOT_VERIFIED",
    "raw_artifact": "TC-Z03-EXT/external/openmeteo_20260825.json",
    "raw_artifact_integrity": { ... },
    "provenance_reference": "TC-Z03-EXT/qa/qa_EXT.json",
    "provenance": { ... },
    "idempotency_key": "IK-TC-Z03-EXT-OPENMETEO-OBS001",
    "hardware_verified": False
}
```

### Conclusion

`context_id` was never introduced into the V2.2 contract. The schema's `additionalProperties: false` constraint actively prohibits it. The canonical representation of NULL context is **field omission**.

---

## 6. Contract Comparison

| Requirement | V2.2 Contract | Observed Evidence | Result |
|-------------|---------------|-------------------|--------|
| `observation_id` | Caller-supplied, pattern-validated, persisted verbatim | Stable across POST → GET | **PASS** |
| `canonical_record_id` | Generated as `CR-<uuid>`, never regenerated on replay | Asserted in 3 dedicated tests; `None` on 409 | **PASS** |
| `contract_version` | `const: "2.2"` | `2.2` in schema, tests, and retrieval | **PASS** |
| `schema_version` | `"2.2"` (optional, retained for compatibility) | `2.2` in payload and retrieval | **PASS** |
| `context_id` | Not in contract; `additionalProperties: false` | Zero occurrences across all branches | **PASS — OMITTED** |

---

## 7. Silent Contract Drift Check

| Check | Result |
|-------|--------|
| Field renamed | NONE |
| Field omitted unexpectedly | NONE |
| Field unexpectedly added | NONE |
| `null` converted to empty string | NONE |
| `null` converted to missing | NOT APPLICABLE (`context_id` was never present) |
| `null` converted to another ID | NONE |
| `observation_id` substituted | NONE — verbatim preservation verified |
| `canonical_record_id` substituted | NONE — generated once, stable on replay |
| IDs regenerated | NONE — replay returns same `canonical_record_id` |
| Version changed | NONE — `const: "2.2"` |
| Schema changed | NONE |
| Downstream representation altered | NOT VERIFIED |

```text
Silent contract drift: NONE
```

---

## 8. Audit Limitations

| Limitation | Detail |
|------------|--------|
| Deployed runtime | API was not live during this audit. All evidence is drawn from the authoritative V2.2 schema, test assertions, persistence code, and database schema. |
| Downstream handoff | No downstream consumer was tested. Downstream representation stability is not verified. |

---

## 9. Final Verdict

```text
GROUP 1 CONTRACT & IDENTITY CLEARANCE: CONDITIONAL PASS
```

| Check | Result |
|-------|--------|
| `observation_id` stable | ✅ PASS |
| `canonical_record_id` stable | ✅ PASS |
| `contract_version = 2.2` | ✅ PASS |
| `schema_version = 2.2` | ✅ PASS |
| `context_id` = FIELD OMITTED | ✅ PASS |
| Silent contract drift | ✅ NONE |
| Deployed runtime verified | ⚠️ NOT AVAILABLE |
| Downstream handoff verified | ⚠️ NOT VERIFIED |

---

## 10. Handover Note for Rahil

The `context_id` question is **closed**.

The V2.2 Group 1 runtime contract uses **field omission** — `context_id` does not exist in the schema, the Pydantic models, the persistence layer, the database schema, or any test fixture. The schema enforces `additionalProperties: false`, which means sending `"context_id": null` would fail validation.

The canonical representation of NULL context in V2.2 is the **complete absence of the field**.
