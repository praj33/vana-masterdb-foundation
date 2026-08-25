-- ============================================================
-- Migration 0003 — Add 'external_api' to capture_method constraint
--
-- Safe, idempotent forward migration for PostgreSQL (vana_masterdb).
-- Updates observation table capture_method CHECK constraint to support
-- the approved V2.2 external_api capture method.
-- ============================================================

DO $$
BEGIN
    -- Drop existing inline/table check constraint on capture_method if present
    IF EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'observation_capture_method_check'
    ) THEN
        ALTER TABLE observation DROP CONSTRAINT observation_capture_method_check;
    END IF;

    IF EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'chk_observation_capture_method'
    ) THEN
        ALTER TABLE observation DROP CONSTRAINT chk_observation_capture_method;
    END IF;

    -- Add updated capture_method CHECK constraint supporting external_api
    ALTER TABLE observation
    ADD CONSTRAINT chk_observation_capture_method
    CHECK (capture_method IN ('aerial', 'ground', 'sensor', 'site_evidence', 'external_api') OR capture_method IS NULL);
END $$;

-- Record schema version update in schema_version table
INSERT INTO schema_version (version, description)
VALUES (
    '0.8.1',
    'Updates capture_method CHECK constraint to support external_api for V2.2 external non-flight feeds.'
)
ON CONFLICT (version) DO NOTHING;
