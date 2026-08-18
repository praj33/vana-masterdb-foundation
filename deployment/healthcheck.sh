#!/usr/bin/env bash
# =============================================================
# deployment/healthcheck.sh — VANA MasterDB Foundation
#
# Quick health probe for a running deployment.
# Usage:
#   chmod +x deployment/healthcheck.sh
#   ./deployment/healthcheck.sh [API_BASE_URL]
#
# Default API_BASE_URL is http://localhost:8010
# =============================================================

set -euo pipefail

API_BASE="${1:-http://localhost:8013}"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

echo ""
echo "[healthcheck] VANA MasterDB Foundation — Health Check"
echo "[healthcheck] API: ${API_BASE}"
echo ""

# ---- Docker services ----
if command -v docker > /dev/null 2>&1; then
  echo "[healthcheck] Docker Compose service status:"
  docker compose -f docker-compose.production.yml ps 2>/dev/null || \
  docker compose ps 2>/dev/null || \
  echo "  (docker compose not available or not running)"
  echo ""
fi

# ---- HTTP health probe ----
if ! command -v curl > /dev/null 2>&1; then
  echo "[healthcheck] WARNING: curl not available — skipping HTTP check."
else
  echo "[healthcheck] HTTP /health probe..."
  HEALTH=$(curl -sf "${API_BASE}/health" 2>/dev/null || echo "UNREACHABLE")
  if echo "$HEALTH" | grep -q "healthy"; then
    echo "[healthcheck] API: OK — ${HEALTH}"
  else
    echo "[healthcheck] API: UNHEALTHY or not reachable"
    echo "  Response: ${HEALTH}"
    echo ""
    echo "  Troubleshooting:"
    echo "    docker compose -f docker-compose.production.yml logs vana-api"
    echo "    docker compose -f docker-compose.production.yml logs vana-db"
  fi
fi

echo ""
echo "[healthcheck] Done."
