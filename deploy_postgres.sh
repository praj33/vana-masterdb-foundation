#!/usr/bin/env bash
# deploy_postgres.sh — run this ON THE VM, not locally.
#
# Deploys VANA schema v0.3 against the real Postgres/PostGIS instance
# and proves it with the same insert/retrieve/idempotency/rejection
# evidence used in every local proof so far — except this time it's
# the real thing, not a SQLite stand-in.
#
# Usage:
#   export VANA_DATABASE_URL="postgresql://user:pass@host:5432/vana"
#   ./deploy_postgres.sh
#
# Requires: python3, pip, network access to the Postgres host,
# PostGIS extension installable by the connecting user (CREATE
# EXTENSION requires superuser or a role granted that privilege —
# if this fails on permissions, ask whoever administers the VM to
# run `CREATE EXTENSION IF NOT EXISTS postgis;` once, manually, then
# re-run this script).

set -euo pipefail

if [[ -z "${VANA_DATABASE_URL:-}" ]]; then
    echo "ERROR: VANA_DATABASE_URL is not set."
    echo "  export VANA_DATABASE_URL=\"postgresql://user:pass@host:5432/vana\""
    exit 1
fi

if [[ "$VANA_DATABASE_URL" != postgresql://* && "$VANA_DATABASE_URL" != postgres://* ]]; then
    echo "ERROR: VANA_DATABASE_URL doesn't look like a Postgres URL: $VANA_DATABASE_URL"
    exit 1
fi

echo "[deploy] Target: $(echo "$VANA_DATABASE_URL" | sed -E 's#(://[^:]+):[^@]+@#\1:****@#')"  # mask password in output

echo "[deploy] Checking for psycopg2..."
python3 -c "import psycopg2" 2>/dev/null || {
    echo "[deploy] psycopg2 not found — installing psycopg2-binary..."
    pip install psycopg2-binary --quiet
}

echo
echo "=== [deploy] Step 1/3: init_db.py (applies migrations/0001_init.sql) ==="
python3 init_db.py

echo
echo "=== [deploy] Step 2/3: seed.py (real Thane Creek seed record) ==="
python3 seed.py

echo
echo "=== [deploy] Step 3/3: test_roundtrip.py (retrieval + idempotency + rejection evidence) ==="
python3 test_roundtrip.py

echo
echo "[deploy] SUCCESS — schema v0.3 deployed and proven against real Postgres/PostGIS."
echo "[deploy] Re-run this script any time — init_db.py and seed.py are both no-ops on repeat."
