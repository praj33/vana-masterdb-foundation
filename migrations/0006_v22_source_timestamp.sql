-- ============================================================
-- Migration 0006 — Add source_timestamp to observation
--
-- Safe, idempotent forward migration for PostgreSQL (vana_masterdb).
-- Adds source_timestamp column to observation table for V2.2 persistence parity.
-- ============================================================

DO $$
BEGIN
    -- 1. Add source_timestamp column to observation if not present
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'observation' AND column_name = 'source_timestamp'
    ) THEN
        ALTER TABLE observation ADD COLUMN source_timestamp TIMESTAMPTZ;
    END IF;
END $$;

-- 2. Record schema version 0.9.2 update
INSERT INTO schema_version (version, description)
VALUES (
    '0.9.2',
    'Adds observation.source_timestamp column for V2.2 persistence parity.'
)
ON CONFLICT (version) DO NOTHING;
