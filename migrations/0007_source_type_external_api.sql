-- ============================================================
-- Migration 0007 — Add EXTERNAL_API to source.source_type CHECK
--
-- The V2.2 external_api capture method was added to the observation
-- table's capture_method CHECK in migration 0003, but the source
-- table's source_type CHECK was never updated to allow EXTERNAL_API.
-- This causes a CHECK violation on PostgreSQL for any external_api
-- observation (e.g. MU-Z01-EXT-OPENMETEO-OBS001).
--
-- Safe, idempotent forward migration for PostgreSQL (vana_masterdb).
-- ============================================================

DO $$
DECLARE
    conname TEXT;
BEGIN
    -- Find the auto-named CHECK constraint on source.source_type
    SELECT c.conname INTO conname
    FROM pg_constraint c
    JOIN pg_class t ON c.conrelid = t.oid
    JOIN pg_namespace n ON t.relnamespace = n.oid
    WHERE t.relname = 'source'
      AND n.nspname = 'public'
      AND c.contype = 'c'
      AND pg_get_constraintdef(c.oid) LIKE '%GROUP3_FIELD_CAPTURE%';

    IF conname IS NOT NULL THEN
        EXECUTE format('ALTER TABLE source DROP CONSTRAINT %I', conname);
    END IF;

    -- Add updated CHECK constraint with EXTERNAL_API included
    ALTER TABLE source
    ADD CONSTRAINT chk_source_source_type
    CHECK (source_type IN (
        'SCIENTIFIC_LITERATURE',
        'GOVERNMENT_DATASET',
        'EARTH_OBSERVATION',
        'INSTITUTIONAL',
        'SYNTHETIC_TEST',
        'GROUP3_FIELD_CAPTURE',
        'EXTERNAL_API'
    ));
END $$;

-- Record schema version update
INSERT INTO schema_version (version, description)
VALUES (
    '0.9.3',
    'Adds EXTERNAL_API to source.source_type CHECK constraint for V2.2 external_api observations.'
)
ON CONFLICT (version) DO NOTHING;
