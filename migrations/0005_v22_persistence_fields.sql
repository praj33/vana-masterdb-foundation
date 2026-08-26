-- ============================================================
-- Migration 0005 — Add provenance_reference & contract_version to observation
--
-- Safe, idempotent forward migration for PostgreSQL (vana_masterdb).
-- Adds provenance_reference and contract_version columns to observation table.
-- ============================================================

DO $$
BEGIN
    -- 1. Add provenance_reference column to observation if not present
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'observation' AND column_name = 'provenance_reference'
    ) THEN
        ALTER TABLE observation ADD COLUMN provenance_reference TEXT;
    END IF;

    -- 2. Add contract_version column to observation if not present
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'observation' AND column_name = 'contract_version'
    ) THEN
        ALTER TABLE observation ADD COLUMN contract_version TEXT DEFAULT '2.2';
    END IF;
END $$;

-- 3. Record schema version 0.9.1 update
INSERT INTO schema_version (version, description)
VALUES (
    '0.9.1',
    'Adds observation.provenance_reference and observation.contract_version columns for V2.2 persistence parity.'
)
ON CONFLICT (version) DO NOTHING;
