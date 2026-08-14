CREATE TABLE IF NOT EXISTS ingestion_idempotency (
    idempotency_key       TEXT PRIMARY KEY,
    observation_id        TEXT NOT NULL,
    request_fingerprint   TEXT NOT NULL,
    http_status           INTEGER NOT NULL,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);
INSERT INTO schema_version (version, description) VALUES ('0.1.1', 'Rukkaiya: request-level ingestion idempotency store') ON CONFLICT DO NOTHING;
