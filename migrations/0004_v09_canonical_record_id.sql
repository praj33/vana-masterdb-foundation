-- ============================================================
-- Migration 0004 — Add canonical_record_id to observation & idempotency_record
--
-- Persistence-generated authoritative Group 1 identity (CR-<uuid>).
-- Safe, idempotent forward migration for PostgreSQL (vana_masterdb).
-- ============================================================

DO $$
BEGIN
    -- 1. Add canonical_record_id column to observation if not present
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'observation' AND column_name = 'canonical_record_id'
    ) THEN
        ALTER TABLE observation ADD COLUMN canonical_record_id TEXT UNIQUE;
    END IF;

    -- 2. Backfill canonical_record_id for any existing observations using CR- + UUID
    UPDATE observation
    SET canonical_record_id = 'CR-' || gen_random_uuid()
    WHERE canonical_record_id IS NULL;

    -- 3. Enforce NOT NULL constraint on observation.canonical_record_id
    ALTER TABLE observation
    ALTER COLUMN canonical_record_id SET NOT NULL;

    -- 4. Add canonical_record_id column to idempotency_record if not present
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'idempotency_record' AND column_name = 'canonical_record_id'
    ) THEN
        ALTER TABLE idempotency_record ADD COLUMN canonical_record_id TEXT REFERENCES observation(canonical_record_id);
    END IF;

    -- 5. Backfill idempotency_record from observation table
    UPDATE idempotency_record ir
    SET canonical_record_id = o.canonical_record_id
    FROM observation o
    WHERE ir.observation_id = o.observation_id
      AND ir.canonical_record_id IS NULL;

    -- 6. Add index on idempotency_record(canonical_record_id)
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'idx_idempotency_canonical'
    ) AND NOT EXISTS (
        SELECT 1 FROM pg_class WHERE relname = 'idx_idempotency_canonical'
    ) THEN
        CREATE INDEX idx_idempotency_canonical ON idempotency_record(canonical_record_id);
    END IF;
END $$;

-- 7. Record schema version 0.9 update
INSERT INTO schema_version (version, description)
VALUES (
    '0.9',
    'Adds observation.canonical_record_id (UNIQUE NOT NULL) as Group 1 authoritative identity, and updates idempotency_record.'
)
ON CONFLICT (version) DO NOTHING;
