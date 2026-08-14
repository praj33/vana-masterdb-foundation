-- ============================================================
-- VANA MasterDB Foundation — Schema v0.1
-- Group 1 (Kavy) — Day 1 Sprint, 12 Aug 2026
-- Run this against MASTERDB_DATABASE_URL (Postgres) on the VM.
-- Requires PostGIS extension.
-- ============================================================

CREATE EXTENSION IF NOT EXISTS postgis;

-- ------------------------------------------------------------
-- Schema versioning — every migration gets a row here.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS schema_version (
    version         TEXT PRIMARY KEY,
    applied_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    description     TEXT NOT NULL
);

INSERT INTO schema_version (version, description)
VALUES ('0.1', 'Initial VANA foundation: source, dataset, observation, measurement, geography, provenance, processing_run')
ON CONFLICT (version) DO NOTHING;

-- ------------------------------------------------------------
-- SOURCE REGISTRY — every piece of evidence gets a source_id
-- before anything downstream can reference it.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS source (
    source_id       TEXT PRIMARY KEY,          -- e.g. 'SRC-THANECREEK-2023-CARBONSTOCK-01'
    source_type     TEXT NOT NULL CHECK (source_type IN
                        ('SCIENTIFIC_LITERATURE','GOVERNMENT_DATASET','EARTH_OBSERVATION',
                         'INSTITUTIONAL','SYNTHETIC_TEST')),
    title           TEXT NOT NULL,
    publisher       TEXT,
    url             TEXT,
    citation        TEXT,
    retrieved_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_synthetic    BOOLEAN NOT NULL DEFAULT FALSE,   -- ground rule 5: SYNTHETIC/TEST must be explicit
    notes           TEXT
);

-- ------------------------------------------------------------
-- DATASET REGISTRY — a defined extract/product derived from
-- one or more sources.
-- ------------------------------------------------------------
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

-- ------------------------------------------------------------
-- GEOGRAPHY — spatial reference for any observation.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS geography (
    geo_id          TEXT PRIMARY KEY,
    place_name      TEXT NOT NULL,
    geom            GEOMETRY(Geometry, 4326) NOT NULL,   -- WGS84
    crs             TEXT NOT NULL DEFAULT 'EPSG:4326',
    notes           TEXT
);

-- ------------------------------------------------------------
-- OBSERVATION — one recorded scientific observation, always
-- traceable to a dataset (and through it, a source) and a
-- geography.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS observation (
    observation_id      TEXT PRIMARY KEY,
    dataset_id           TEXT NOT NULL REFERENCES dataset(dataset_id),
    geo_id                TEXT REFERENCES geography(geo_id),
    observation_date     DATE,
    species               TEXT,
    observation_type      TEXT NOT NULL,   -- e.g. 'CARBON_STOCK', 'BIOMASS', 'WATER_QUALITY'
    confidence            TEXT CHECK (confidence IN ('HIGH','MEDIUM','LOW','UNCERTAIN')),
    conflict_flag         BOOLEAN NOT NULL DEFAULT FALSE,
    conflict_notes        TEXT,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ------------------------------------------------------------
-- MEASUREMENT — the actual quantitative value(s) attached to
-- an observation. Kept separate from observation so one
-- observation can carry multiple measured quantities without
-- schema changes.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS measurement (
    measurement_id     TEXT PRIMARY KEY,
    observation_id      TEXT NOT NULL REFERENCES observation(observation_id),
    metric_name          TEXT NOT NULL,     -- e.g. 'above_ground_biomass'
    value                 NUMERIC NOT NULL,
    unit                  TEXT NOT NULL,      -- e.g. 'Mg/ha'
    method                TEXT,                -- e.g. 'allometry', 'allometry_remote_sensing_integrated'
    original_value_text  TEXT,                -- verbatim as stated in source, before any transform
    transform_applied     TEXT,               -- explicit note if value was converted; NULL if none
    created_at             TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ------------------------------------------------------------
-- PROCESSING RUN — every time raw source material passes
-- through Samachar/ingestion, a run record is created so the
-- transformation itself is reproducible and auditable.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS processing_run (
    run_id            TEXT PRIMARY KEY,
    source_id          TEXT NOT NULL REFERENCES source(source_id),
    dataset_id          TEXT REFERENCES dataset(dataset_id),
    pipeline_stage        TEXT NOT NULL,  -- 'EXTRACT','NORMALISE','CONTEXTUALISE','VALIDATE','PROVENANCE','INGEST'
    status                 TEXT NOT NULL CHECK (status IN ('DONE','PARTIAL','BLOCKED','FAILED')),
    input_ref              TEXT,
    output_ref              TEXT,
    error_detail             TEXT,
    started_at                TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at               TIMESTAMPTZ,
    actor                       TEXT NOT NULL   -- who/what ran this stage
);

-- ------------------------------------------------------------
-- PROVENANCE — explicit source -> record trace. This is the
-- table replay/audit queries hit to answer "where did this
-- number come from."
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS provenance (
    provenance_id     TEXT PRIMARY KEY,
    measurement_id      TEXT NOT NULL REFERENCES measurement(measurement_id),
    source_id             TEXT NOT NULL REFERENCES source(source_id),
    run_id                 TEXT REFERENCES processing_run(run_id),
    derivation_note          TEXT NOT NULL,  -- human-readable: "extracted verbatim", "converted units cm->m", etc
    recorded_at                TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Helpful index for the acceptance-test retrieval query.
CREATE INDEX IF NOT EXISTS idx_provenance_measurement ON provenance(measurement_id);
CREATE INDEX IF NOT EXISTS idx_measurement_observation ON measurement(observation_id);
CREATE INDEX IF NOT EXISTS idx_observation_dataset ON observation(dataset_id);
CREATE INDEX IF NOT EXISTS idx_geography_geom ON geography USING GIST (geom);
