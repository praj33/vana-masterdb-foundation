-- ============================================================
-- Migration 0001 ΓÇö VANA Schema v0.2
-- Supersedes v0.1 (Day 1 sprint). Incorporates architecture
-- decisions A-D agreed in REUSE_AND_GAP_MAP.md review:
--   A) field_observation_meta as a SEPARATE table (Option 2)
--   B) geo_location is observation-specific by default (scope column
--      added so zone-level rows remain possible, explicitly, later)
--   C) observation_date -> observed_at, full timestamp with timezone
--   D) new capture_method column; observation_type is NOT reused
--      for Group 3's aerial/ground/sensor/site_evidence values
-- Plus: raw_artifact table (Kavy-owned per Day-5 boundary agreement
-- with Rukkaiya, who owns the hashing/integrity logic that writes
-- into it).
--
-- Written for PostgreSQL + PostGIS (the real target). This exact
-- file is what runs on the VM. init_db.py additionally supports a
-- SQLite fallback (see migrations/0001_init_sqlite.sql) purely so
-- this can be proven end-to-end without VM/network access ΓÇö the
-- table shapes are kept identical field-for-field between the two.
-- ============================================================

CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS schema_version (
    version         TEXT PRIMARY KEY,
    applied_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    description     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS source (
    source_id       TEXT PRIMARY KEY,
    source_type     TEXT NOT NULL CHECK (source_type IN
                        ('SCIENTIFIC_LITERATURE','GOVERNMENT_DATASET','EARTH_OBSERVATION',
                         'INSTITUTIONAL','SYNTHETIC_TEST','GROUP3_FIELD_CAPTURE')),
    title           TEXT NOT NULL,
    publisher       TEXT,
    url             TEXT,
    citation        TEXT,
    retrieved_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_synthetic    BOOLEAN NOT NULL DEFAULT FALSE,
    notes           TEXT
);

CREATE TABLE IF NOT EXISTS dataset (
    dataset_id      TEXT PRIMARY KEY,
    dataset_name    TEXT NOT NULL,
    source_id       TEXT NOT NULL REFERENCES source(source_id),
    methodology     TEXT,
    schema_version  TEXT NOT NULL REFERENCES schema_version(version),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    status          TEXT NOT NULL DEFAULT 'REGISTERED' CHECK (status IN
                        ('REGISTERED','VALIDATED','REJECTED','UNCERTAIN'))
);

-- Decision B: scope distinguishes a point tied to one observation
-- from a shared zone row. Default is POINT ΓÇö one geography row per
-- observation is now the norm, not the exception.
CREATE TABLE IF NOT EXISTS geo_location (
    geo_id          TEXT PRIMARY KEY,
    scope           TEXT NOT NULL DEFAULT 'POINT' CHECK (scope IN ('POINT','ZONE')),
    place_name      TEXT NOT NULL,
    geom            GEOMETRY(Geometry, 4326) NOT NULL,
    crs             TEXT NOT NULL DEFAULT 'EPSG:4326',
    notes           TEXT
);

-- Decision C: observed_at replaces observation_date, full timestamptz.
-- Decision D: capture_method added; observation_type keeps its
-- original meaning (what was measured), unchanged.
CREATE TABLE IF NOT EXISTS observation (
    observation_id      TEXT PRIMARY KEY,       -- caller-supplied (e.g. Group 3's TC-Z03-F02-LIDAR-OBS001)
    dataset_id           TEXT NOT NULL REFERENCES dataset(dataset_id),
    geo_id                TEXT REFERENCES geo_location(geo_id),
    observed_at           TIMESTAMPTZ,            -- Decision C
    capture_method        TEXT,                    -- Decision D: 'aerial'|'ground'|'sensor'|'site_evidence'|... nullable for non-field sources
    species               TEXT,
    observation_type      TEXT NOT NULL,          -- unchanged meaning: what was measured, e.g. 'CARBON_STOCK','BIOMASS'
    quality_status         TEXT NOT NULL DEFAULT 'CAPTURED' CHECK (quality_status IN
                                ('RAW','CAPTURED','VALIDATED','REJECTED','UNCERTAIN','INGESTED')),
    confidence            TEXT CHECK (confidence IN ('HIGH','MEDIUM','LOW','UNCERTAIN')),
    conflict_flag         BOOLEAN NOT NULL DEFAULT FALSE,
    conflict_notes        TEXT,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Decision A, Option 2: separate table, not columns bolted onto
-- observation. Only field-captured observations populate this.
CREATE TABLE IF NOT EXISTS field_observation_meta (
    observation_id      TEXT PRIMARY KEY REFERENCES observation(observation_id),
    device_id             TEXT,
    operator               TEXT,
    mission_id              TEXT,
    accuracy                 NUMERIC,          -- nullable; never invent a value (per team rule)
    accuracy_unit            TEXT,
    calibration_status         TEXT CHECK (calibration_status IN
                                    ('CALIBRATED','UNCALIBRATED','NOT_VERIFIED')),
    processing_status           TEXT,
    notes                         TEXT
);

-- Decision F (new, Sanskar's Day-6 API integration review): Group 3's
-- V1.0 payload includes an image observation with a non-numeric
-- measurement value and no unit. NUMERIC NOT NULL / unit NOT NULL
-- can't represent that. Adds a data_type discriminator and a
-- value_text column instead of forcing every measurement to be a
-- number.
CREATE TABLE IF NOT EXISTS measurement (
    measurement_id     TEXT PRIMARY KEY,
    observation_id      TEXT NOT NULL REFERENCES observation(observation_id),
    metric_name          TEXT NOT NULL,
    data_type             TEXT NOT NULL DEFAULT 'NUMERIC' CHECK (data_type IN ('NUMERIC','TEXT','BOOLEAN')),
    value                 NUMERIC,           -- required iff data_type='NUMERIC'
    value_text            TEXT,               -- required iff data_type IN ('TEXT','BOOLEAN'); e.g. classification label
    unit                  TEXT,               -- nullable now ΓÇö only meaningful for NUMERIC measurements
    method                TEXT,
    original_value_text  TEXT,
    transform_applied     TEXT,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (
        (data_type = 'NUMERIC' AND value IS NOT NULL) OR
        (data_type IN ('TEXT','BOOLEAN') AND value_text IS NOT NULL)
    )
);

-- New: raw artifact reference (Section 9 of REUSE_AND_GAP_MAP.md).
-- Kavy owns this table's existence/shape; Rukkaiya owns the
-- hashing/integrity logic that populates content_hash.
CREATE TABLE IF NOT EXISTS raw_artifact (
    artifact_id       TEXT PRIMARY KEY,
    observation_id      TEXT NOT NULL REFERENCES observation(observation_id),
    artifact_type         TEXT NOT NULL,   -- e.g. 'IMAGE','LIDAR_SCAN','SENSOR_LOG','DOCUMENT'
    storage_ref             TEXT NOT NULL,   -- durable pointer (Bucket URI, file path, etc.) ΓÇö not the bytes themselves
    content_hash             TEXT,             -- populated by Rukkaiya's integrity layer; nullable until then
    hash_algorithm             TEXT,
    captured_at                  TIMESTAMPTZ,
    notes                          TEXT
);

CREATE TABLE IF NOT EXISTS processing_run (
    run_id            TEXT PRIMARY KEY,
    source_id          TEXT NOT NULL REFERENCES source(source_id),
    dataset_id          TEXT REFERENCES dataset(dataset_id),
    pipeline_stage        TEXT NOT NULL,
    status                 TEXT NOT NULL CHECK (status IN ('DONE','PARTIAL','BLOCKED','FAILED')),
    input_ref              TEXT,
    output_ref              TEXT,
    error_detail             TEXT,
    started_at                TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at               TIMESTAMPTZ,
    actor                       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS provenance (
    provenance_id     TEXT PRIMARY KEY,
    measurement_id      TEXT NOT NULL REFERENCES measurement(measurement_id),
    source_id             TEXT NOT NULL REFERENCES source(source_id),
    run_id                 TEXT REFERENCES processing_run(run_id),
    derivation_note          TEXT NOT NULL,
    recorded_at                TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_provenance_measurement ON provenance(measurement_id);
CREATE INDEX IF NOT EXISTS idx_measurement_observation ON measurement(observation_id);
CREATE INDEX IF NOT EXISTS idx_observation_dataset ON observation(dataset_id);
CREATE INDEX IF NOT EXISTS idx_raw_artifact_observation ON raw_artifact(observation_id);
CREATE INDEX IF NOT EXISTS idx_geo_location_geom ON geo_location USING GIST (geom);

-- New (v0.4): supports Rukkaiya's Idempotency-Key + request-fingerprint
-- contract ΓÇö exact replay returns the existing result; same key with
-- a different fingerprint is a real conflict (409), not a silent
-- no-op. Table, not a column on observation, because the idempotency
-- key is an API-layer concept (may differ from observation_id) and
-- because it needs its own created_at independent of the observation.
CREATE TABLE IF NOT EXISTS idempotency_record (
    idempotency_key       TEXT PRIMARY KEY,
    observation_id          TEXT NOT NULL REFERENCES observation(observation_id),
    request_fingerprint       TEXT NOT NULL,   -- hash of the canonical request payload
    fingerprint_algorithm       TEXT NOT NULL DEFAULT 'sha256',
    first_response_status         TEXT NOT NULL,  -- e.g. 'CREATED', so a replay can return the same status
    created_at                      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_idempotency_observation ON idempotency_record(observation_id);

INSERT INTO schema_version (version, description)
VALUES ('0.3', 'Renames geography table to geo_location (PostGIS reserves the type name "geography" ΓÇö CREATE TABLE geography collides with it and fails on real Postgres, per Hemanth''s finding). Adds field_observation_meta, raw_artifact, capture_method, observed_at, geo_location.scope, measurement.data_type/value_text per REUSE_AND_GAP_MAP.md decisions A-D and Sanskar''s image-observation finding')
ON CONFLICT (version) DO NOTHING;

INSERT INTO schema_version (version, description)
VALUES ('0.4', 'Adds idempotency_record (Idempotency-Key + request-fingerprint contract, per Rukkaiya''s identity/idempotency design)')
ON CONFLICT (version) DO NOTHING;
