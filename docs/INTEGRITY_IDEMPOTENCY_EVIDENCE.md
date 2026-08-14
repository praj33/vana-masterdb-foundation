# Integrity & Idempotency Evidence

**Branch:** `feature/integrity-idempotency`  
**Date:** 2026-08-14  
**Environment:** Windows 10, Python 3.12.10, pytest 9.0.3

---

# Scope & Architecture Distinction

This document captures evidence for the Group 1 integrity foundation slice:

- Deterministic observation **logical identity** (`OBS-<32 hex chars>`)
- Request-level **idempotency** via `Idempotency-Key` + body fingerprint
- Single-transaction ingestion with full provenance chain
- Raw-artifact content addressing (`sha256:<hex>|ref:<path>`)
- Failure-mode handling (validation errors leave DB unchanged; failed-then-valid retry)

### Key Architectural & Implementation Boundaries

1. **Production / Canonical VANA MasterDB Schema:**  
   The canonical production database design is defined in PostgreSQL / PostGIS format in `schema (1).sql`.
2. **Current Executable Test Implementation:**  
   The Python implementation under `src/vana_integrity/` uses a local SQLite adapter to execute all acceptance, idempotency, failure-mode, and provenance tests in isolated in-memory test databases.
3. **Scope of 0 → 1 → 1 Proof:**  
   The 0 → 1 → 1 observation count transition is a real, persisted SQLite test execution proof verifying local storage contracts and idempotency enforcement logic. It is **NOT** a claim that production Postgres VM ingestion has already been deployed.

---

## Observation Identity Definition

Logical identity is computed from canonical fields only (no timestamps or arrival time):

| Field | Notes |
|-------|-------|
| `dataset_id` | From `dataset` block |
| `geo_id` | Nullable |
| `observation_date` | |
| `species` | Nullable |
| `observation_type` | |
| `confidence` | Nullable |
| `measurements` | Sorted by `(metric_name, value, unit, method)` |

**Format:** `OBS-` + first 32 hex characters of SHA-256 over sorted JSON of the canonical payload.

### Deterministic Identity vs. Synthetic Test Alias

- **Deterministic Logical Identity:** `OBS-bfd90d26981f4c9e09bf3a938c55424a` (computed SHA-256 hash over canonical fields).
- **Synthetic Acceptance-Test Alias:** `OBSERVATION-001`.

> [!IMPORTANT]
> `OBSERVATION-001` is strictly a synthetic acceptance-test alias permitted only when `source_type=SYNTHETIC_TEST`, `is_synthetic=true`, and the payload matches the fixed acceptance fixture. `OBSERVATION-001` must **NOT** be interpreted as the production logical identity format or value.

### Computed values (acceptance fixture)

```
LOGICAL_IDENTITY=OBS-bfd90d26981f4c9e09bf3a938c55424a
REQUEST_FINGERPRINT=db36b12355223ed5ee7525c901f2babf23968779cc3c043244f668aaffea9f4e
RAW_SHA256=ad9e6ce51e6d29babe310499173b95a5f18d8156b62202e7392946264849648f
RAW_REF=fixtures/synthetic_observation_001.json
```

Stored observation ID for the synthetic fixture: `OBSERVATION-001` (alias), with logical identity validated against the computed hash above.

---

## Idempotency Mechanism

1. Client sends `Idempotency-Key` header (optional but required for acceptance proof).
2. Server computes `request_fingerprint` = SHA-256 of normalized JSON body (`sort_keys=True`, compact separators).
3. On ingest, `check_idempotency()` looks up `ingestion_idempotency` table:
   - **Key + fingerprint match:** return prior result, HTTP 200, no new rows.
   - **Key + fingerprint mismatch:** raise `IdempotencyConflictError`, HTTP 409.
   - **No key:** duplicate detection falls back to observation_id existence check.
4. Successful first ingest records `(idempotency_key, observation_id, request_fingerprint, http_status=201)`.

Migration: `migrations/001_ingestion_idempotency.sql`

---

## Duplicate / Retry / Failure Handling

| Scenario | HTTP | DB effect |
|----------|------|-----------|
| First valid submission | 201 | Creates full chain (source, dataset, observation, measurements, processing_run, provenance) |
| Exact duplicate (same key + body) | 200 | Observation count unchanged |
| Same key, different body | 409 | Observation count unchanged |
| Malformed payload (missing measurements) | 422 | All counts unchanged |
| Failed validation then valid retry | 201 then 200 | Exactly one observation after recovery |

All writes occur inside `BEGIN IMMEDIATE` … `COMMIT` with rollback on any exception.

---

## Provenance Handling

Each measurement gets a `provenance` row linking:

- `measurement_id` → `source_id` → `run_id` → `derivation_note`

`processing_run.input_ref` stores `sha256:<digest>|ref:<uri-or-path>` from the raw artifact block.

Idempotent replay does **not** create additional provenance rows (`test_provenance_preserved_after_retry`).

---

## Raw-Artifact Reference / Integrity

- Content digest: SHA-256 of `raw_artifact.content` bytes
- Stored as: `sha256:ad9e6ce51e6d29babe310499173b95a5f18d8156b62202e7392946264849648f|ref:fixtures/synthetic_observation_001.json`
- Same content → same hash; modified content → different hash (`test_raw_artifact.py`)

---

## Test Commands

```powershell
pip install -r requirements.txt -q
pytest -v
pytest -v -s tests/test_acceptance_001.py
pytest -v tests/test_idempotency.py tests/test_identity.py
pytest -v tests/test_failure_modes.py tests/test_provenance.py tests/test_raw_artifact.py
```

0→1→1 proof script (with `PYTHONPATH=src`):

```python
import json
from pathlib import Path
from fastapi.testclient import TestClient
from vana_integrity.api import create_app
from vana_integrity.db import connect, apply_schema, count_observations

conn = connect(':memory:')
apply_schema(conn)
payload = json.loads(Path('fixtures/synthetic_observation_001.json').read_text())
app, _ = create_app(conn=conn)
client = TestClient(app)
headers = {'Idempotency-Key': 'acceptance-001-key'}
before = count_observations(conn)
client.post('/ingest/observations', json=payload, headers=headers)
first = count_observations(conn)
client.post('/ingest/observations', json=payload, headers=headers)
second = count_observations(conn)
print(f'BEFORE_COUNT={before}')
print(f'FIRST_SUBMISSION_COUNT={first}')
print(f'SECOND_SUBMISSION_COUNT={second}')
print('RESULT=PASS' if second==1 and first==1 and before==0 else 'RESULT=FAIL')
print('PROOF=0 -> 1 -> 1')
```

---

## Actual Test Results

### Full suite (`pytest -v`)

```
============================= test session starts =============================
platform win32 -- Python 3.12.10, pytest-9.0.3, pluggy-1.6.0 -- C:\Users\rukka\AppData\Local\Programs\Python\Python312\python.exe
cachedir: .pytest_cache
rootdir: C:\Users\rukka\OneDrive\Desktop\Build\vana-masterdb-foundation
configfile: pytest.ini
testpaths: tests
plugins: anyio-4.13.0, asyncio-1.4.0, cov-7.1.0
asyncio: mode=Mode.STRICT, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 19 items

tests/test_acceptance_001.py::test_acceptance_001_idempotency_proof PASSED [  5%]
tests/test_failure_modes.py::test_malformed_payload_leaves_counts_unchanged PASSED [ 10%]
tests/test_failure_modes.py::test_failed_then_valid_retry_creates_exactly_one PASSED [ 15%]
tests/test_idempotency.py::test_first_submission_zero_to_one PASSED      [ 21%]
tests/test_idempotency.py::test_exact_duplicate_stays_one PASSED         [ 26%]
tests/test_idempotency.py::test_request_retry_with_idempotency_key PASSED [ 31%]
tests/test_idempotency.py::test_different_observation_increments_count PASSED [ 36%]
tests/test_idempotency.py::test_same_key_different_body_returns_409 PASSED [ 42%]
tests/test_identity.py::test_participating_fields_documented PASSED      [ 47%]
tests/test_identity.py::test_logical_identity_is_deterministic PASSED    [ 52%]
tests/test_identity.py::test_measurement_ordering_affects_identity PASSED [ 57%]
tests/test_identity.py::test_synthetic_alias_allowed_for_fixture PASSED  [ 63%]
tests/test_identity.py::test_synthetic_alias_rejected_for_non_synthetic PASSED [ 68%]
tests/test_identity.py::test_identity_excludes_timestamps PASSED         [ 73%]
tests/test_provenance.py::test_provenance_chain_created PASSED           [ 78%]
tests/test_provenance.py::test_provenance_preserved_after_retry PASSED   [ 84%]
tests/test_raw_artifact.py::test_same_content_same_hash PASSED           [ 89%]
tests/test_raw_artifact.py::test_modified_content_different_hash PASSED  [ 94%]
tests/test_raw_artifact.py::test_input_ref_format_and_parse PASSED       [100%]

============================== warnings summary ===============================
(... deprecation warnings for starlette multipart and FastAPI on_event ...)

======================= 19 passed, 21 warnings in 0.18s =======================
```

### Acceptance (`pytest -v -s tests/test_acceptance_001.py`)

```
tests/test_acceptance_001.py::test_acceptance_001_idempotency_proof PASSED
======================== 1 passed, 3 warnings in 0.03s ========================
```

### Idempotency + Identity (`pytest -v tests/test_idempotency.py tests/test_identity.py`)

```
tests/test_idempotency.py::test_first_submission_zero_to_one PASSED      [  9%]
tests/test_idempotency.py::test_exact_duplicate_stays_one PASSED         [ 18%]
tests/test_idempotency.py::test_request_retry_with_idempotency_key PASSED [ 27%]
tests/test_idempotency.py::test_different_observation_increments_count PASSED [ 36%]
tests/test_idempotency.py::test_same_key_different_body_returns_409 PASSED [ 45%]
tests/test_identity.py::test_participating_fields_documented PASSED      [ 54%]
tests/test_identity.py::test_logical_identity_is_deterministic PASSED    [ 63%]
tests/test_identity.py::test_measurement_ordering_affects_identity PASSED [ 72%]
tests/test_identity.py::test_synthetic_alias_allowed_for_fixture PASSED  [ 81%]
tests/test_identity.py::test_synthetic_alias_rejected_for_non_synthetic PASSED [ 90%]
tests/test_identity.py::test_identity_excludes_timestamps PASSED         [100%]

======================= 11 passed, 11 warnings in 0.11s =======================
```

### Failure modes + Provenance + Raw artifact

```
tests/test_failure_modes.py::test_malformed_payload_leaves_counts_unchanged PASSED [ 14%]
tests/test_failure_modes.py::test_failed_then_valid_retry_creates_exactly_one PASSED [ 28%]
tests/test_provenance.py::test_provenance_chain_created PASSED           [ 42%]
tests/test_provenance.py::test_provenance_preserved_after_retry PASSED   [ 57%]
tests/test_raw_artifact.py::test_same_content_same_hash PASSED           [ 71%]
tests/test_raw_artifact.py::test_modified_content_different_hash PASSED  [ 85%]
tests/test_raw_artifact.py::test_input_ref_format_and_parse PASSED       [100%]

======================== 7 passed, 9 warnings in 0.11s ========================
```

---

## Actual Before/After Counts — 0→1→1 Proof

Direct script output (in-memory SQLite, fixture `fixtures/synthetic_observation_001.json`, key `acceptance-001-key`):

```
BEFORE_COUNT=0
FIRST_SUBMISSION_COUNT=1
SECOND_SUBMISSION_COUNT=1
RESULT=PASS
PROOF=0 -> 1 -> 1
LOGICAL_IDENTITY=OBS-bfd90d26981f4c9e09bf3a938c55424a
REQUEST_FINGERPRINT=db36b12355223ed5ee7525c901f2babf23968779cc3c043244f668aaffea9f4e
RAW_SHA256=ad9e6ce51e6d29babe310499173b95a5f18d8156b62202e7392946264849648f
RAW_REF=fixtures/synthetic_observation_001.json
```

**Explicit evidence:** observation count transitions **0 → 1 → 1** across first submission (HTTP 201) and idempotent replay (HTTP 200).

> [!NOTE]
> This 0 → 1 → 1 proof is a real persisted SQLite acceptance test proof demonstrating code-level storage contracts and idempotency enforcement logic. It is **NOT** a claim that production Postgres VM ingestion has already been deployed.

---

## Failure-Mode Evidence

| Test | Assertion |
|------|-----------|
| `test_malformed_payload_leaves_counts_unchanged` | HTTP 422; observation/measurement/provenance counts unchanged |
| `test_failed_then_valid_retry_creates_exactly_one` | Invalid source_type → 422, count=0; valid → 201 count=1; retry → 200 count=1 |
| `test_same_key_different_body_returns_409` | HTTP 409 on fingerprint conflict; count stays 1 |

All failure-mode tests **PASSED** (see full suite output above).

---

## Remaining Integration Dependencies

| Dependency | Status |
|------------|--------|
| Postgres + PostGIS production database wiring (`MASTERDB_DATABASE_URL`) | Production wiring is pending; schema in `schema (1).sql`; current executable test suite uses SQLite adapter |
| Idempotency migration (`migrations/001_ingestion_idempotency.sql`) | Migration has not yet been applied to the VM |
| Ingestion API endpoint | Ingestion API is currently local/test-only (`/ingest/observations`) |
| Raw artifact storage | Raw artifact blob storage is not implemented (content digest hash + ref stored; blob upload mechanism not implemented) |
| FastAPI lifespan handler modernization | Replace deprecated `@app.on_event("shutdown")` with lifespan event handlers |
| Spatial geography validation | Schema in `schema (1).sql`; PostGIS `geo_id` spatial resolution not exercised in local test slice |

---

## Git State (evidence capture time)

```
On branch feature/integrity-idempotency
Your branch is up to date with 'origin/feature/integrity-idempotency'.

Changes to be committed:
  new file:   schema (1).sql

Untracked files:
  fixtures/
  migrations/
  pytest.ini
  requirements.txt
  src/
  tests/
  docs/INTEGRITY_IDEMPOTENCY_EVIDENCE.md
```

`git diff --stat` and `git diff`: no unstaged modifications to tracked files (only staged `schema (1).sql` as new file).
