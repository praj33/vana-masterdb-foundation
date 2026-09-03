-- Official historical government dataset records remain separate from
-- Group 3 observations. This migration adds no production data.

CREATE TABLE IF NOT EXISTS official_forest_cover_record (
    record_id TEXT PRIMARY KEY,
    dataset_id TEXT NOT NULL REFERENCES dataset(dataset_id),
    source_record_id TEXT,
    assessment_year INTEGER NOT NULL CHECK (assessment_year BETWEEN 1000 AND 9999),
    geography_level TEXT NOT NULL CHECK (geography_level IN ('STATE', 'DISTRICT')),
    state TEXT NOT NULL,
    district TEXT,
    boundary_reference TEXT,
    forest_cover_area NUMERIC,
    forest_cover_percentage NUMERIC CHECK (forest_cover_percentage IS NULL OR (forest_cover_percentage >= 0 AND forest_cover_percentage <= 100)),
    very_dense_forest_area NUMERIC,
    moderately_dense_forest_area NUMERIC,
    open_forest_area NUMERIC,
    mangrove_area NUMERIC,
    unit TEXT,
    methodology TEXT,
    quality_status TEXT NOT NULL DEFAULT 'UNVERIFIED' CHECK (quality_status IN ('UNVERIFIED', 'EXTRACTED', 'VALIDATED', 'REJECTED')),
    provenance_reference TEXT NOT NULL,
    request_fingerprint TEXT NOT NULL,
    idempotency_key TEXT UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK ((geography_level = 'DISTRICT' AND district IS NOT NULL) OR (geography_level = 'STATE' AND district IS NULL))
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_official_forest_cover_natural_key
    ON official_forest_cover_record (dataset_id, geography_level, state, COALESCE(district, ''), COALESCE(source_record_id, ''));

INSERT INTO schema_version (version, description)
VALUES ('0.9.4', 'Adds official historical forest-cover records without changing Group 3 observations')
ON CONFLICT (version) DO NOTHING;