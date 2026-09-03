# VANA Schema v0.2 — Data Dictionary

**Owner:** Kavy — Canonical Schema & Database Engineer
**Date:** 19 August 2026 (Day 6)
**Supersedes:** v0.1 (Day 1). Adds fields agreed in `REUSE_AND_GAP_MAP.md`
decisions A–D, plus `raw_artifact`.
**Migration:** `migrations/0001_init.sql` (Postgres/PostGIS — the real
target) and `migrations/0001_init_sqlite.sql` (field-identical local
proof backend, used because this session has no VM/network access).

---

## Setup

```bash
# Local proof (default):
python3 init_db.py && python3 seed.py && python3 test_roundtrip.py

# Real VM target:
export VANA_DATABASE_URL="postgresql://user:pass@vm-host:5432/vana"
python3 init_db.py && python3 seed.py && python3 test_roundtrip.py
```

Re-running `init_db.py` is a no-op after the first successful run —
applied migrations are tracked in `_migrations_log`, so a fresh
engineer can run the same command twice safely.

---

## Tables

### `official_forest_cover_record`

Official historical government records are stored separately from
Group 3 `observation` rows. The table references the existing `dataset` and
keeps administrative geography and assessment year without inventing point
coordinates or field metadata.

| Column | Type | Notes |
|---|---|---|
| `record_id` | TEXT PK | Deterministic from dataset, geography, and source row identity |
| `dataset_id` | TEXT FK | Existing official dataset |
| `source_record_id` | TEXT | Source row/code where supplied |
| `assessment_year` | INTEGER | Historical assessment year |
| `geography_level` | TEXT | `STATE` or `DISTRICT` |
| `state`, `district` | TEXT | District is required only for district records |
| `boundary_reference` | TEXT | Authoritative boundary/code reference; no fake coordinates |
| forest-cover fields | NUMERIC | Nullable source values with explicit units |
| `unit` | TEXT | Unit for area values |
| `quality_status` | TEXT | `UNVERIFIED`, `EXTRACTED`, `VALIDATED`, `REJECTED` |
| `provenance_reference` | TEXT | Required source/provenance pointer |
| `request_fingerprint`, `idempotency_key` | TEXT | Replay/conflict protection |

### `schema_version`
Tracks the schema's own version history (not per-migration-file — see
`_migrations_log` for that). One row per released schema version.

| Column | Type | Notes |
|---|---|---|
| `version` | TEXT PK | e.g. `'0.2'` |
| `applied_at` | TIMESTAMPTZ | |
| `description` | TEXT | what changed in this version |

### `source`
Every piece of evidence — literature, government dataset, sensor feed,
synthetic fixture — gets a row here before anything downstream can
reference it.

| Column | Type | Notes |
|---|---|---|
| `source_id` | TEXT PK | caller-assigned, e.g. `SRC-THANECREEK-2023-CARBONSTOCK-01` |
| `source_type` | TEXT | `SCIENTIFIC_LITERATURE`, `GOVERNMENT_DATASET`, `EARTH_OBSERVATION`, `INSTITUTIONAL`, `SYNTHETIC_TEST`, `GROUP3_FIELD_CAPTURE` |
| `title`, `publisher`, `url`, `citation` | TEXT | |
| `retrieved_at` | TIMESTAMPTZ | |
| `is_synthetic` | BOOLEAN | **must be TRUE for any non-real fixture — enforced by convention, not a DB constraint** |
| `notes` | TEXT | e.g. flag unconfirmed citation details |

### `dataset`
A defined extract/product derived from one source.

| Column | Type | Notes |
|---|---|---|
| `dataset_id` | TEXT PK | |
| `dataset_name` | TEXT | |
| `source_id` | TEXT FK → `source` | |
| `methodology` | TEXT | |
| `schema_version` | TEXT FK → `schema_version` | |
| `status` | TEXT | `REGISTERED`, `VALIDATED`, `REJECTED`, `UNCERTAIN` |

### `geo_location` — **renamed in v0.3 (was `geography`)**
**Note on the rename:** PostGIS reserves `geography` as a built-in type name (used to store geographic coordinates). `CREATE TABLE geography` collides with it and fails outright once the PostGIS extension is loaded on real Postgres — this table was renamed to `geo_location` to fix that (Hemanth caught this before it hit the VM).
| Column | Type | Notes |
|---|---|---|
| `geo_id` | TEXT PK | |
| `scope` | TEXT | **new.** `POINT` (default) or `ZONE`. Decision B: field-captured observations get their own `POINT` row; literature/aggregate records may reasonably share a `ZONE` row. This is a discipline, not an enforced constraint — reviewers should check new inserts follow it. |
| `place_name` | TEXT | |
| `geom` (Postgres) / `lat`,`lon` (SQLite) | GEOMETRY(4326) / REAL | |
| `crs` | TEXT | default `EPSG:4326` |

### `observation` — **changed in v0.2**
| Column | Type | Notes |
|---|---|---|
| `observation_id` | TEXT PK | **caller-supplied**, not generated — e.g. Group 3's `TC-Z03-F02-LIDAR-OBS001`. This is the idempotency key. |
| `dataset_id` | TEXT FK → `dataset` | required |
| `geo_id` | TEXT FK → `geo_location` | nullable |
| `observed_at` | TIMESTAMPTZ | **renamed from `observation_date`, now full timestamp (Decision C)**. Nullable — literature sources may only have a year. |
| `capture_method` | TEXT | **new (Decision D)**. `aerial`, `ground`, `sensor`, `site_evidence`, etc. — *how* it was captured. Nullable for non-field sources. |
| `species` | TEXT | |
| `observation_type` | TEXT | **unchanged meaning** — *what* was measured, e.g. `BIOMASS`, `CARBON_STOCK`. Do not put capture-method values here. |
| `quality_status` | TEXT | **new.** `RAW`, `CAPTURED`, `VALIDATED`, `REJECTED`, `UNCERTAIN`, `INGESTED`. Default `CAPTURED`. |
| `confidence` | TEXT | `HIGH`, `MEDIUM`, `LOW`, `UNCERTAIN` |
| `is_synthetic` | BOOLEAN | **new (v0.7).** Default `FALSE`. Observation-level synthetic/test flag — distinct from `source.is_synthetic`: a real source can still produce a synthetic/test observation (e.g. a fixture run against a real device), so this needs its own flag rather than inheriting the source's. |
| `conflict_flag`, `conflict_notes` | BOOLEAN, TEXT | |

### `field_observation_meta` — **new table (Decision A, Option 2)**
One row per observation, only populated for field-captured records.
Kept separate from `observation` so literature/aggregate records don't
carry a wall of NULLs.

| Column | Type | Notes |
|---|---|---|
| `observation_id` | TEXT PK, FK → `observation` | |
| `device_id`, `operator`, `mission_id` | TEXT | |
| `accuracy` | NUMERIC | **nullable — never invent a value.** Leave NULL if not verified. |
| `accuracy_unit` | TEXT | |
| `calibration_status` | TEXT | `CALIBRATED`, `UNCALIBRATED`, `NOT_VERIFIED` |
| `processing_status` | TEXT | free text for now — Sanskar's API layer may formalize this |
| `notes` | TEXT | |

### `measurement`
The actual quantitative value(s) for an observation. One observation
→ many measurements (e.g. two methods for the same metric).

| Column | Type | Notes |
|---|---|---|
| `measurement_id` | TEXT PK | **deterministic** — hash of `observation_id + metric_name + method`, so re-submission of the same measurement is a no-op rather than a duplicate |
| `observation_id` | TEXT FK → `observation` | |
| `metric_name`, `value`, `unit`, `method` | | |
| `original_value_text` | TEXT | verbatim as stated in source, before any transform |
| `transform_applied` | TEXT | explicit note if converted; NULL if none — **no silent semantic changes** |

### `raw_artifact` — **new table**
Durable reference to original raw evidence (imagery, LiDAR scans,
sensor logs). **Kavy owns this table's existence/shape; Rukkaiya owns
the hashing/integrity logic that populates `content_hash`** — agreed
boundary from the Day-5 reuse-map review.

| Column | Type | Notes |
|---|---|---|
| `artifact_id` | TEXT PK | deterministic, hash of `observation_id + artifact_type` |
| `observation_id` | TEXT FK → `observation` | |
| `artifact_type` | TEXT | `IMAGE`, `LIDAR_SCAN`, `SENSOR_LOG`, `DOCUMENT`, ... |
| `storage_ref` | TEXT | durable pointer (Bucket URI, file path) — **not the raw bytes themselves** |
| `content_hash`, `hash_algorithm` | TEXT | nullable until Rukkaiya's integrity layer populates them |
| `captured_at` | TIMESTAMPTZ | |

### `processing_run`
One row per pipeline stage execution — makes every transformation
answerable ("what processing produced this").

| Column | Type | Notes |
|---|---|---|
| `run_id` | TEXT PK | |
| `source_id` | TEXT FK → `source` | |
| `dataset_id` | TEXT FK → `dataset`, nullable | |
| `pipeline_stage` | TEXT | `EXTRACT`, `NORMALISE`, `CONTEXTUALISE`, `VALIDATE`, `PROVENANCE`, `INGEST`, `SEED`, `TEST_INGEST` |
| `status` | TEXT | `DONE`, `PARTIAL`, `BLOCKED`, `FAILED` |
| `input_ref`, `output_ref`, `error_detail` | TEXT | |
| `actor` | TEXT | who/what ran this stage |

### `provenance`
Explicit source → record trace. This is what answers "where did this
number come from."

| Column | Type | Notes |
|---|---|---|
| `provenance_id` | TEXT PK | deterministic, hash of `measurement_id + source_id` |
| `measurement_id` | TEXT FK → `measurement` | |
| `source_id` | TEXT FK → `source` | |
| `run_id` | TEXT FK → `processing_run`, nullable | |
| `derivation_note` | TEXT | human-readable: "extracted verbatim", "SYNTHETIC/TEST fixture", etc. |

---

## Idempotency mechanism (implements Decision E jointly with Rukkaiya)

- `observation.observation_id` is caller-supplied and is the
  idempotency key — no server-generated ID for observations. This
  matches Group 3's own stable-ID contract (`TC-Z03-F02-LIDAR-OBS001`)
  directly; no translation layer needed.
- `insert_observation()` checks existence first; a repeat submission
  with the same `observation_id` is a no-op, not an error and not a
  duplicate. Proven: `0 → 1 → 1 → 1` across three identical submission
  attempts (see `EVIDENCE.txt`).
- `measurement_id`, `provenance_id`, and `artifact_id` are all
  deterministic hashes of their parent IDs + content, so partial
  re-submission (same observation, same measurements) is also safe.

## What is NOT yet proven

- **This has not run against the real VM Postgres/PostGIS instance.**
  Every table shape and constraint above is written for Postgres
  (`0001_init.sql`) and mirrored exactly in the SQLite proof — the SQL
  is ready to run as-is, but only the SQLite path has actually been
  executed, because this session has no network route to the VM.
- **`geography.scope` discipline is not DB-enforced** — nothing stops
  a future insert from putting a shared `ZONE` row under a real field
  capture. It's a convention agreed in the reuse map, not a
  constraint. Worth a check constraint or app-layer validation before
  Group 3 integration goes live.
- **`content_hash` on `raw_artifact` is genuinely NULL** in the seed
  data — that's Rukkaiya's layer to populate, not faked here.
