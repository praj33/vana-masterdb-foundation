# GROUP 1 CLOSING-DAY BASELINE

**Date:** 2026-08-29  
**Execution Time:** 11:02:30 IST  
**Author:** Group 1 Canonical Observation / Runtime Verification Engineer  
**Role:** Canonical Observation / Runtime Verification Engineer  
**Target:** VANA Closing-Day Acceptance Gate (12:00 PM Group 1 Gate / 3:00 PM VANA Hard Gate)

---

## 1. Repository and Branch Identity

| Property | Value |
|---|---|
| **Repository** | `praj33/vana-masterdb-foundation` |
| **Workspace Root** | `C:\Users\rukka\OneDrive\Desktop\Build\vana-masterdb-foundation` |
| **Active Feature Branch** | `feature/integrity-idempotency` |
| **Active Head Commit** | `6c4dd73` (`finalize Group 1 contract identity check`) |
| **Upstream Tracked Branch** | `origin/feature/integrity-idempotency` |
| **Canonical Target Branch** | `origin/main` (commit `7722fd7` / `fix: return V2.2 schema_version from observation contract`) |
| **Working Tree Status** | Clean on production source; active feature branch updated with T11/T16 closures and GET endpoint support |

---

## 2. Deployed Endpoint & Runtime Environment

| Component | Specification |
|---|---|
| **Service Name** | VANA Integrity Ingestion & Retrieval API |
| **Active Runtime Framework** | FastAPI (v0.139.0) + Starlette + TestClient |
| **Active Deployed Ingestion Route** | `POST /ingest/observations` |
| **Active Deployed Retrieval Route** | `GET /observations/{observation_id}` and `GET /ingest/observations/{observation_id}` |
| **Health Check Route** | `GET /health` |
| **Database Persistence Engine** | SQLite native connection with Foreign Keys enabled (`PRAGMA foreign_keys = ON`, `row_factory = sqlite3.Row`) |
| **Schema Migration Applied** | `migrations/0001_init_sqlite.sql` (mirrored from PostgreSQL target DDL `migrations/0001_init.sql`) |
| **Persistence Isolation** | Atomic transactional ingestion (`BEGIN IMMEDIATE` / `COMMIT` / `ROLLBACK`) |
| **Runtime Adapter Note** | Native SQLite adapter serves as the authoritative, deterministic runtime verification boundary. Target PostgreSQL DDL with PostGIS is maintained for VM production infrastructure. |

---

## 3. Current Schema Version & Observation Contract

| Parameter | Current Runtime Value | Contract Specification |
|---|---|---|
| **Dataset Schema Version** | `0.4` | Enforced against registered registry versions (`0.3`, `0.4`). Unregistered versions (e.g., `99.0`) rejected with HTTP 422. |
| **Contract Version** | `v0.4` / Canonical Normalized Relational Foundation | Full 10-table relational schema preserving source, dataset, geo_location, observation, field_meta, measurement, raw_artifact, processing_run, provenance, idempotency_record. |
| **Observation Identity Semantics** | Caller-supplied primary key | Required, non-empty, string pattern preserved verbatim. No synthetic hash prefix (`OBS-<hash>`) generated. Nested `observation.observation_id` supported. |
| **Canonical Record Identity** | `observation_id` verbatim | Exact 1:1 mapping between caller logical identity and persisted canonical primary key. |
| **Canonical Record Retrieval** | `GET /observations/{observation_id}` | Returns complete composite canonical record including dataset metadata, source metadata, field observation metadata, exact GPS coordinates, all measurement metrics, raw artifact pointers with SHA-256 hashes, and provenance derivations. |
| **Idempotency Guarantee** | `0 → 1 → 1` | Verified via `Idempotency-Key` header and deterministic body fingerprinting (SHA-256 canonical JSON). Replays return HTTP 200 with identical record; payload mutations with identical key return HTTP 409 conflict. |

---

## 4. Known T11 & T16 Status Summary

| Issue ID | Historical Concern | Closing-Day Final Verification Status | Evidence Summary |
|---|---|---|---|
| **T11** | SQLite runtime lacked `schema_version` registry validation; unregistered versions (`99.0`) were accepted. | **RESOLVED / PASS** | `src/vana_integrity/validation.py` enforces `VALID_SCHEMA_VERSIONS = {"0.3", "0.4"}` and `migrations/0001_init_sqlite.sql` seeds `schema_version`. Unregistered version `99.0` returns HTTP 422 with atomic rollback. |
| **T16** | `GROUP3_FIELD_CAPTURE` was rejected by runtime validation while permitted by PostgreSQL DDL. | **RESOLVED / PASS** | `src/vana_integrity/validation.py` includes `GROUP3_FIELD_CAPTURE` in `VALID_SOURCE_TYPES`. Real field capture payloads ingest successfully with HTTP 201 (`is_synthetic=0`). |

---

## 5. Known Blockers & Limitations

| Item | Classification | Impact | Mitigation / Status |
|---|---|---|---|
| **PostgreSQL VM Direct Network Route** | Environmental | Direct VM PostGIS connection requires dedicated cloud VPC route. | Native SQLite adapter mirrors exact field-by-field schema and semantics, providing 100% deterministic local verification. |
| **Group 4 / Downstream Integration** | Ready for Handoff | Group 4 requires frozen endpoint, request/response schema, and identity contract. | Contract frozen and documented in `GROUP1_DEPLOYED_API_CONTRACT_FREEZE.md` and `GROUP1_GROUP4_LIVE_RUNTIME_HANDOFF.md`. |
