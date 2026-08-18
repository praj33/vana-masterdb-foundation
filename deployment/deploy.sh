#!/usr/bin/env bash
# =============================================================
# deployment/deploy.sh — VANA MasterDB Foundation VM deploy
#
# Usage:
#   chmod +x deployment/deploy.sh
#   ./deployment/deploy.sh
#
# Prerequisites on the VM:
#   - Docker Engine  (>= 24)
#   - Docker Compose plugin  (>= 2.24)
#   - .env file present at project root (copied from .env.example)
# =============================================================

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

echo ""
echo "=============================================="
echo "  VANA MasterDB Foundation — Deploying"
echo "  Project root: $(pwd)"
echo "=============================================="
echo ""

# ---- pre-flight checks ----
if [ ! -f ".env" ]; then
  echo "[deploy] ERROR: .env file not found. Copy .env.example and fill in credentials:"
  echo "  cp .env.example .env && nano .env"
  exit 1
fi

if ! command -v docker > /dev/null 2>&1; then
  echo "[deploy] ERROR: Docker is not installed or not in PATH."
  exit 1
fi

if ! docker compose version > /dev/null 2>&1; then
  echo "[deploy] ERROR: Docker Compose plugin not available. Install docker-compose-plugin."
  exit 1
fi

echo "[deploy] Building images..."
docker compose -f docker-compose.production.yml build

echo ""
echo "[deploy] Starting services (PostgreSQL + PostGIS, then VANA API)..."
docker compose -f docker-compose.production.yml up -d

echo ""
echo "[deploy] Waiting for services to be healthy (up to 90s)..."
TIMEOUT=90
ELAPSED=0
while [ $ELAPSED -lt $TIMEOUT ]; do
  DB_STATUS=$(docker inspect --format='{{.State.Health.Status}}' vana_db 2>/dev/null || echo "missing")
  API_STATUS=$(docker inspect --format='{{.State.Health.Status}}' vana_api 2>/dev/null || echo "missing")

  if [ "$DB_STATUS" = "healthy" ] && [ "$API_STATUS" = "healthy" ]; then
    echo "[deploy] ✓ Both services are healthy."
    break
  fi

  echo "[deploy] DB: ${DB_STATUS} | API: ${API_STATUS} — waiting..."
  sleep 5
  ELAPSED=$((ELAPSED + 5))
done

if [ "$API_STATUS" != "healthy" ]; then
  echo "[deploy] WARNING: API did not reach healthy state within ${TIMEOUT}s."
  echo "[deploy] Check logs with: docker compose -f docker-compose.production.yml logs vana-api"
fi

# Source .env to read VANA_API_PORT
source .env
PORT="${VANA_API_PORT:-8013}"

echo ""
echo "=============================================="
echo "  Deployment complete."
echo "  VANA API:     http://$(hostname -I | awk '{print $1}'):${PORT}"
echo "  Health check: http://$(hostname -I | awk '{print $1}'):${PORT}/health"
echo "  Swagger UI:   http://$(hostname -I | awk '{print $1}'):${PORT}/docs"
echo "=============================================="
echo ""
echo "  Next step: run the end-to-end idempotency acceptance test:"
echo "    ./deployment/run_e2e_test.sh"
echo ""
