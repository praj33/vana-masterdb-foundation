#!/usr/bin/env bash
# =============================================================
# deployment/run_e2e_test.sh
#
# Proves the Group 3 → VANA idempotency contract against a
# running PostgreSQL + PostGIS instance:
#
#   Round 1 (first submission)  → HTTP 201  count=1
#   Round 2 (exact replay)      → HTTP 200  count=1  (IDEMPOTENT_REPLAY)
#   Round 3 (same key, mutated) → HTTP 409  count=1  (IDEMPOTENCY_CONFLICT)
#
# i.e. 0 → 1 → 1 (record count never exceeds 1)
#
# Usage:
#   chmod +x deployment/run_e2e_test.sh
#   ./deployment/run_e2e_test.sh [API_BASE_URL]
#
# Default API_BASE_URL is http://localhost:8010
# Pass the VM's public URL as the first argument when running
# against a remote host.
# =============================================================

set -euo pipefail

API_BASE="${1:-http://localhost:8013}"
IDEMPOTENCY_KEY="E2E-TC-Z03-F02-LIDAR-OBS001-$(date +%s)"

# ---- colour helpers ----
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

pass() { echo -e "${GREEN}[PASS]${NC} $*"; }
fail() { echo -e "${RED}[FAIL]${NC} $*"; FAILURES=$((FAILURES + 1)); }
info() { echo -e "${YELLOW}[INFO]${NC} $*"; }

FAILURES=0

echo ""
echo "=============================================="
echo "  VANA MasterDB — E2E Idempotency Proof"
echo "  API: ${API_BASE}"
echo "  Idempotency-Key: ${IDEMPOTENCY_KEY}"
echo "=============================================="
echo ""

# ---- health check ----
info "Health check..."
HEALTH=$(curl -sf "${API_BASE}/health" || echo "UNREACHABLE")
if echo "$HEALTH" | grep -q '"status":"healthy"'; then
  pass "Health OK: ${HEALTH}"
else
  fail "API is not healthy or not reachable. Response: ${HEALTH}"
  echo "Aborting — check deployment."
  exit 1
fi

echo ""

# ---- Canonical Group 3 synthetic fixture ----
# observation_id is unique per test run via the timestamp in the key
OBS_ID="TC-Z03-F02-LIDAR-E2E-$(date +%s)"

PAYLOAD=$(cat <<EOF
{
  "observation_id": "${OBS_ID}",
  "survey_id": "TC",
  "zone_id": "Z03",
  "flight_id": "F02",
  "sensor_id": "LIDAR",
  "observation_seq": "OBS001",
  "device_id": "G3-LIDAR-001",
  "timestamp": "2026-08-13T09:14:22Z",
  "latitude": 19.1288,
  "longitude": 72.9421,
  "observation_type": "aerial",
  "measurement": 4.7,
  "parameter": "canopy_height",
  "unit": "m",
  "accuracy": "NOT VERIFIED",
  "calibration_status": "NOT_VERIFIED",
  "raw_artifact_reference": {
    "path": "TC-Z03-F02/drone/pointcloud_F02_e2e.las",
    "checksum_sha256": "f7254999689ae5b530a0006d0fb6765df0317973504e8c5d1b393bfa5826cf9d",
    "artifact_type": "point_cloud"
  },
  "quality_status": "VALIDATED",
  "processing_status": "chm_derived",
  "provenance": {
    "device_id": "G3-LIDAR-001",
    "operator": "E2E-test-runner",
    "mission_id": "TC-Z03-F02",
    "captured_at": "2026-08-13T09:14:22Z",
    "raw_artifact": "TC-Z03-F02/drone/pointcloud_F02_e2e.las",
    "qa_record": "TC-Z03-F02/qa/qa_F02.json"
  },
  "tidal_state": null,
  "trace_id": null,
  "idempotency_key": "${IDEMPOTENCY_KEY}"
}
EOF
)

MUTATED_PAYLOAD=$(cat <<EOF
{
  "observation_id": "${OBS_ID}",
  "survey_id": "TC",
  "zone_id": "Z03",
  "flight_id": "F02",
  "sensor_id": "LIDAR",
  "observation_seq": "OBS001",
  "device_id": "G3-LIDAR-001",
  "timestamp": "2026-08-13T09:14:22Z",
  "latitude": 19.1288,
  "longitude": 72.9421,
  "observation_type": "aerial",
  "measurement": 99.9,
  "parameter": "canopy_height",
  "unit": "m",
  "accuracy": "NOT VERIFIED",
  "calibration_status": "NOT_VERIFIED",
  "raw_artifact_reference": {
    "path": "TC-Z03-F02/drone/pointcloud_F02_e2e.las",
    "checksum_sha256": "f7254999689ae5b530a0006d0fb6765df0317973504e8c5d1b393bfa5826cf9d",
    "artifact_type": "point_cloud"
  },
  "quality_status": "VALIDATED",
  "processing_status": "chm_derived",
  "provenance": {
    "device_id": "G3-LIDAR-001",
    "operator": "E2E-test-runner",
    "mission_id": "TC-Z03-F02",
    "captured_at": "2026-08-13T09:14:22Z",
    "raw_artifact": "TC-Z03-F02/drone/pointcloud_F02_e2e.las",
    "qa_record": "TC-Z03-F02/qa/qa_F02.json"
  },
  "tidal_state": null,
  "trace_id": null,
  "idempotency_key": "${IDEMPOTENCY_KEY}"
}
EOF
)

# ============================================================
# Round 1 — First submission → 201 ACCEPTED, count = 1
# ============================================================
info "Round 1: First submission (expect HTTP 201, status=ACCEPTED)"
R1=$(curl -s -w "\n%{http_code}" -X POST "${API_BASE}/observations" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: ${IDEMPOTENCY_KEY}" \
  -d "$PAYLOAD")
R1_BODY=$(echo "$R1" | head -n -1)
R1_CODE=$(echo "$R1" | tail -n 1)
R1_STATUS=$(echo "$R1_BODY" | grep -o '"status":"[^"]*"' | head -1 | cut -d'"' -f4)

echo "  HTTP ${R1_CODE}  body: ${R1_BODY}"

[ "$R1_CODE" = "201" ] && pass "Round 1: HTTP 201 ✓" || fail "Round 1: expected 201, got ${R1_CODE}"
[ "$R1_STATUS" = "ACCEPTED" ] && pass "Round 1: status=ACCEPTED ✓" || fail "Round 1: expected ACCEPTED, got ${R1_STATUS}"

# ============================================================
# Round 2 — Exact replay → 200 IDEMPOTENT_REPLAY, count = 1
# ============================================================
echo ""
info "Round 2: Exact replay (expect HTTP 200, status=IDEMPOTENT_REPLAY)"
R2=$(curl -s -w "\n%{http_code}" -X POST "${API_BASE}/observations" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: ${IDEMPOTENCY_KEY}" \
  -d "$PAYLOAD")
R2_BODY=$(echo "$R2" | head -n -1)
R2_CODE=$(echo "$R2" | tail -n 1)
R2_STATUS=$(echo "$R2_BODY" | grep -o '"status":"[^"]*"' | head -1 | cut -d'"' -f4)

echo "  HTTP ${R2_CODE}  body: ${R2_BODY}"

[ "$R2_CODE" = "200" ] && pass "Round 2: HTTP 200 ✓" || fail "Round 2: expected 200, got ${R2_CODE}"
[ "$R2_STATUS" = "IDEMPOTENT_REPLAY" ] && pass "Round 2: status=IDEMPOTENT_REPLAY ✓" || fail "Round 2: expected IDEMPOTENT_REPLAY, got ${R2_STATUS}"

# ============================================================
# Round 3 — Same key, mutated payload → 409 IDEMPOTENCY_CONFLICT
# ============================================================
echo ""
info "Round 3: Same Idempotency-Key, mutated payload (expect HTTP 409, status=IDEMPOTENCY_CONFLICT)"
R3=$(curl -s -w "\n%{http_code}" -X POST "${API_BASE}/observations" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: ${IDEMPOTENCY_KEY}" \
  -d "$MUTATED_PAYLOAD")
R3_BODY=$(echo "$R3" | head -n -1)
R3_CODE=$(echo "$R3" | tail -n 1)
R3_STATUS=$(echo "$R3_BODY" | grep -o '"status":"[^"]*"' | head -1 | cut -d'"' -f4)

echo "  HTTP ${R3_CODE}  body: ${R3_BODY}"

[ "$R3_CODE" = "409" ] && pass "Round 3: HTTP 409 ✓" || fail "Round 3: expected 409, got ${R3_CODE}"
[ "$R3_STATUS" = "IDEMPOTENCY_CONFLICT" ] && pass "Round 3: status=IDEMPOTENCY_CONFLICT ✓" || fail "Round 3: expected IDEMPOTENCY_CONFLICT, got ${R3_STATUS}"

# ============================================================
# Retrieval check — observation is readable from PostgreSQL
# ============================================================
echo ""
info "Retrieval: GET /observations/${OBS_ID} (expect HTTP 200, status=RETRIEVED)"
R4=$(curl -s -w "\n%{http_code}" "${API_BASE}/observations/${OBS_ID}")
R4_BODY=$(echo "$R4" | head -n -1)
R4_CODE=$(echo "$R4" | tail -n 1)
R4_STATUS=$(echo "$R4_BODY" | grep -o '"status":"[^"]*"' | head -1 | cut -d'"' -f4)

echo "  HTTP ${R4_CODE}  status: ${R4_STATUS}"

[ "$R4_CODE" = "200" ] && pass "Retrieval: HTTP 200 ✓" || fail "Retrieval: expected 200, got ${R4_CODE}"
[ "$R4_STATUS" = "RETRIEVED" ] && pass "Retrieval: status=RETRIEVED ✓" || fail "Retrieval: expected RETRIEVED, got ${R4_STATUS}"

# ============================================================
# Summary
# ============================================================
echo ""
echo "=============================================="
if [ "$FAILURES" -eq 0 ]; then
  echo -e "${GREEN}  ALL CHECKS PASSED — 0 → 1 → 1 PROVEN${NC}"
  echo "  The VANA PostgreSQL + PostGIS deployment is"
  echo "  accepting, replaying, and conflicting correctly."
  EXIT_CODE=0
else
  echo -e "${RED}  ${FAILURES} CHECK(S) FAILED${NC}"
  EXIT_CODE=1
fi
echo "=============================================="
echo ""
exit $EXIT_CODE
