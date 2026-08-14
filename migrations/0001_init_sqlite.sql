-- ============================================================
-- Migration 0001 (SQLite variant) — same fields as 0001_init.sql
-- Differences, purely mechanical (SQLite has no PostGIS/TIMESTAMPTZ/
-- BOOLEAN types): geom -> lat/lon REAL columns, TIMESTAMPTZ -> TEXT
-- (ISO 8601), BOOLEAN -> INTEGER 0/1. No field is added, renamed,
-- or dropped versus the Postgres version.
-- ============================================================

CREATE TABLE IF NOT EXISTS schema_version (
    version TEXT PRIMARY KEY, applied_at TEXT NOT NULL, description TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS source (
    source_id TEXT PRIMARY KEY, source_type TEXT NOT NULL, title TEXT NOT NULL,
    publisher TEXT, url TEXT, citation TEXT, retrieved_at TEXT NOT NULL,
    is_synthetic INTEGER NOT NULL DEFAULT 0, notes TEXT
);

CREATE TABLE IF NOT EXISTS dataset (
    dataset_id TEXT PRIMARY KEY, dataset_name TEXT NOT NULL,
    source_id TEXT NOT NULL REFERENCES source(source_id),
    methodology TEXT, schema_version TEXT NOT NULL, created_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'REGISTERED'
);

CREATE TABLE IF NOT EXISTS geo_location (
    geo_id TEXT PRIMARY KEY, scope TEXT NOT NULL DEFAULT 'POINT',
    place_name TEXT NOT NULL, lat REAL NOT NULL, lon REAL NOT NULL,
    crs TEXT NOT NULL DEFAULT 'EPSG:4326', notes TEXT
);

CREATE TABLE IF NOT EXISTS observation (
    observation_id TEXT PRIMARY KEY,
    dataset_id TEXT NOT NULL REFERENCES dataset(dataset_id),
    geo_id TEXT REFERENCES geo_location(geo_id),
    observed_at TEXT,
    capture_method TEXT,
    species TEXT,
    observation_type TEXT NOT NULL,
    quality_status TEXT NOT NULL DEFAULT 'CAPTURED',
    confidence TEXT,
    conflict_flag INTEGER NOT NULL DEFAULT 0,
    conflict_notes TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS field_observation_meta (
    observation_id TEXT PRIMARY KEY REFERENCES observation(observation_id),
    device_id TEXT, operator TEXT, mission_id TEXT,
    accuracy REAL, accuracy_unit TEXT, calibration_status TEXT,
    processing_status TEXT, notes TEXT
);

CREATE TABLE IF NOT EXISTS measurement (
    measurement_id TEXT PRIMARY KEY,
    observation_id TEXT NOT NULL REFERENCES observation(observation_id),
    metric_name TEXT NOT NULL,
    data_type TEXT NOT NULL DEFAULT 'NUMERIC',
    value REAL, value_text TEXT, unit TEXT, method TEXT,
    original_value_text TEXT, transform_applied TEXT, created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS raw_artifact (
    artifact_id TEXT PRIMARY KEY,
    observation_id TEXT NOT NULL REFERENCES observation(observation_id),
    artifact_type TEXT NOT NULL, storage_ref TEXT NOT NULL,
    content_hash TEXT, hash_algorithm TEXT, captured_at TEXT, notes TEXT
);

CREATE TABLE IF NOT EXISTS processing_run (
    run_id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES source(source_id),
    dataset_id TEXT REFERENCES dataset(dataset_id), pipeline_stage TEXT NOT NULL,
    status TEXT NOT NULL, input_ref TEXT, output_ref TEXT, error_detail TEXT,
    started_at TEXT NOT NULL, finished_at TEXT, actor TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS idempotency_record (
    idempotency_key TEXT PRIMARY KEY,
    observation_id TEXT NOT NULL REFERENCES observation(observation_id),
    request_fingerprint TEXT NOT NULL,
    fingerprint_algorithm TEXT NOT NULL DEFAULT 'sha256',
    first_response_status TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS provenance (
    provenance_id TEXT PRIMARY KEY,
    measurement_id TEXT NOT NULL REFERENCES measurement(measurement_id),
    source_id TEXT NOT NULL REFERENCES source(source_id), run_id TEXT REFERENCES processing_run(run_id),
    derivation_note TEXT NOT NULL, recorded_at TEXT NOT NULL
);
