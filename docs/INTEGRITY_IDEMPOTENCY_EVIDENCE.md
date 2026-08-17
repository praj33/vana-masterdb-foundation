# Integrity & Idempotency Evidence (v0.4 Reconciliation)

**Branch:** `feature/integrity-idempotency`  
**Date:** 2026-08-14  
**Baseline Schema Commit:** `d1be8a1` (v0.4)  
**Environment:** Windows 10, Python 3.12.10, pytest 9.0.3  

---

# Scope & Architecture Alignment

This document captures evidence for the reconciled Group 1 integrity & idempotency implementation aligned with Kavy's canonical **v0.4 schema baseline** (`d1be8a1`):

- **Canonical Logical Identity:** `observation.observation_id` is caller-supplied, required, and persisted verbatim (e.g. Group 3's `TC-Z03-F02-LIDAR-OBS001`). No `OBS-<hash>` is generated.
- **Request-Level Idempotency:** Persisted in `idempotency_record` table using SHA-256 request fingerprinting (`sort_keys=True`, compact separators, UTF-8).
- **Single-Transaction Atomicity:** All writes (`observation`, `geo_location`, `field_observation_meta`, `measurement`, `raw_artifact`, `idempotency_record`, `processing_run`, `provenance`) occur inside an atomic transaction with rollback on failure.
- **Raw-Artifact Content Addressing:** Content hash (`sha256:<digest>|ref:<path>`) stored in `raw_artifact` table.
- **Failure & Conflict Handling:** 201 Created for new submission, 200 Idempotent Replay, 409 Conflict for same key with different body, 422 for validation errors.

> [!IMPORTANT]
> **REAL POSTGRES / VM VALIDATION: PENDING**  
> The 0 → 1 → 1 observation count transition and 22 test verifications are executed via the native SQLite adapter (`migrations/0001_init_sqlite.sql`). Deployment and migration against production Postgres / PostGIS VM instances remain explicit pending dependencies.

---

## Observation Identity Definition

`observation.observation_id` is the canonical logical identity.

- Caller-supplied (passed in request payload or nested observation block).
- Persisted verbatim without prefix/suffix/hash transformations.
- Example: `TC-Z03-F02-LIDAR-OBS001` → persisted as `TC-Z03-F02-LIDAR-OBS001`.

---

## Idempotency Contract (`idempotency_record`)

1. Client sends `Idempotency-Key` header.
2. Server computes `request_fingerprint` = SHA-256 hex digest of normalized canonical JSON body.
3. Server queries `idempotency_record`:
   - **Key + Fingerprint match:** returns prior result with HTTP `200` (Idempotent Replay), creating no duplicate rows.
   - **Key + Fingerprint mismatch:** raises `IdempotencyConflictError`, returning HTTP `409 Conflict` without mutating existing state.
   - **New Key:** persists observation chain and `idempotency_record(idempotency_key, observation_id, request_fingerprint, fingerprint_algorithm='sha256', first_response_status='201')`, returning HTTP `201 Created`.

---

## Database Schema (v0.4)

Canonical Postgres schema: [migrations/0001_init.sql](file:///c:/Users/rukka/OneDrive/Desktop/Build/vana-masterdb-foundation/migrations/0001_init.sql)  
Canonical SQLite schema for tests: [migrations/0001_init_sqlite.sql](file:///c:/Users/rukka/OneDrive/Desktop/Build/vana-masterdb-foundation/migrations/0001_init_sqlite.sql)  

Tables populated during ingestion:
- `source`: Source metadata (`is_synthetic` flag)
- `dataset`: Dataset metadata & methodology
- `geo_location`: Spatial coordinates (`scope='POINT'`)
- `observation`: Primary observation record (`observed_at`, `capture_method`)
- `field_observation_meta`: Optional field metadata (`device_id`, `operator`, `accuracy`)
- `measurement`: Metric readings supporting `NUMERIC`, `TEXT`, and `BOOLEAN` data types
- `raw_artifact`: Storage ref & `content_hash`
- `processing_run`: Ingestion run details
- `provenance`: Measurement-level provenance links
- `idempotency_record`: API idempotency records

---

## Executed Test Results (22/22 PASSED)

```text
============================= test session starts =============================
platform win32 -- Python 3.12.10, pytest-9.0.3, pluggy-1.6.0
rootdir: C:\Users\rukka\OneDrive\Desktop\Build\vana-masterdb-foundation
configfile: pytest.ini
testpaths: tests

tests/test_acceptance_001.py::test_acceptance_001_idempotency_proof PASSED
tests/test_failure_modes.py::test_malformed_payload_leaves_counts_unchanged PASSED
tests/test_failure_modes.py::test_missing_observation_id_rolls_back_atomically PASSED
tests/test_failure_modes.py::test_failed_then_valid_retry_creates_exactly_one PASSED
tests/test_idempotency.py::test_first_submission_zero_to_one PASSED
tests/test_idempotency.py::test_exact_duplicate_stays_one PASSED
tests/test_idempotency.py::test_request_retry_with_idempotency_key PASSED
tests/test_idempotency.py::test_different_observation_increments_count PASSED
tests/test_idempotency.py::test_same_key_different_body_returns_409 PASSED
tests/test_identity.py::test_participating_fields_documented PASSED
tests/test_identity.py::test_caller_supplied_id_accepted PASSED
tests/test_identity.py::test_group3_id_persisted_verbatim PASSED
tests/test_identity.py::test_nested_observation_id_supported PASSED
tests/test_identity.py::test_missing_observation_id_raises_value_error PASSED
tests/test_identity.py::test_no_obs_hash_generated PASSED
tests/test_provenance.py::test_provenance_chain_created PASSED
tests/test_provenance.py::test_provenance_preserved_after_retry PASSED
tests/test_raw_artifact.py::test_same_content_same_hash PASSED
tests/test_raw_artifact.py::test_modified_content_different_hash PASSED
tests/test_raw_artifact.py::test_input_ref_format_and_parse PASSED
tests/test_raw_artifact.py::test_raw_artifact_table_persisted PASSED
tests/test_schema.py::test_v04_schema_entities_persisted PASSED

======================= 22 passed in 0.24s =======================
```

### Mandatory 0 → 1 → 1 Acceptance Proof Output

```text
FIRST_HTTP_STATUS=201
SECOND_HTTP_STATUS=200
BEFORE_COUNT=0
FIRST_SUBMISSION_COUNT=1
SECOND_SUBMISSION_COUNT=1
RESULT=PASS
PROOF=0 -> 1 -> 1
```

---

## Remaining Integration Dependencies

| Dependency | Status |
|------------|--------|
| PostgreSQL + PostGIS production database wiring | **PENDING** (Uses local native SQLite DDL `migrations/0001_init_sqlite.sql`) |
| Application of migration to VM | **PENDING** (`migrations/0001_init.sql` pending execution on production VM) |
| Consumer-facing API deployment | **PENDING** (Ingestion service implemented in `src/vana_integrity/api.py`) |
| Raw artifact blob storage | **PENDING** (Content SHA-256 digest hash + ref stored; object blob store pending) |
| PostGIS spatial validation | **PENDING** (Coordinates stored in `geo_location`; PostGIS spatial indexing pending VM database) |
