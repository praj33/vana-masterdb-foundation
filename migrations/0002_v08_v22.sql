-- ============================================================
-- Migration 0002 — VANA Schema v0.8 Upgrade for V2.2 Integration
--
-- Explicit forward migration script for live PostgreSQL (vana_masterdb).
-- Upgrades an existing v0.6/v0.7 database to v0.8 without data loss or downtime.
--
-- Changes:
--   1. Adds observation.synthetic_state column with DEFAULT 'UNKNOWN'
--   2. Adds CHECK constraint on synthetic_state: ('PHYSICAL','CONTROLLED','SYNTHETIC','SIMULATED','UNKNOWN')
--   3. Preserves existing observation.is_synthetic boolean column & values
--   4. Registers version '0.8' in schema_version table
-- ============================================================

DO $$
BEGIN
    -- 1. Add synthetic_state column to observation table if it does not exist
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'observation'
          AND column_name = 'synthetic_state'
    ) THEN
        ALTER TABLE observation
        ADD COLUMN synthetic_state TEXT NOT NULL DEFAULT 'UNKNOWN';
    END IF;

    -- 2. Ensure is_synthetic column exists (for pre-v0.7 databases)
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'observation'
          AND column_name = 'is_synthetic'
    ) THEN
        ALTER TABLE observation
        ADD COLUMN is_synthetic BOOLEAN NOT NULL DEFAULT FALSE;
    END IF;
END $$;

-- 3. Add CHECK constraint enforcing the five-state synthetic_state vocabulary
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'chk_observation_synthetic_state'
    ) THEN
        ALTER TABLE observation
        ADD CONSTRAINT chk_observation_synthetic_state
        CHECK (synthetic_state IN ('PHYSICAL', 'CONTROLLED', 'SYNTHETIC', 'SIMULATED', 'UNKNOWN'));
    END IF;
END $$;

-- 4. Record schema version 0.8 in schema_version table
INSERT INTO schema_version (version, description)
VALUES (
    '0.8',
    'Adds observation.synthetic_state (PHYSICAL/CONTROLLED/SYNTHETIC/SIMULATED/UNKNOWN) as the canonical field for V2.2. is_synthetic (BOOLEAN) retained as a compatibility field, NOT auto-derived from synthetic_state.'
)
ON CONFLICT (version) DO NOTHING;
