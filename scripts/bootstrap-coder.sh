#!/usr/bin/env bash
set -euo pipefail

# Coder bootstrap helper for the local acceptance environment.
#
# Coder's first login is interactive and the initial user becomes the platform
# owner, so full automation is intentionally avoided. This script is a safe
# documented stub: when CODER_INTERNAL_URL or CODER_API_KEY are missing or
# Coder is unreachable it exits 0 without destructive operations.
#
# To bootstrap Coder for E2E workspace tests, follow the steps in
# tests/e2e/fixtures/coder.md first, then re-run this script.

CODER_INTERNAL_URL="${CODER_INTERNAL_URL:-http://coder:7080}"
CODER_API_KEY="${CODER_API_KEY:-}"

if [[ -z "${CODER_API_KEY}" ]]; then
    echo "CODER_API_KEY is not set; skipping Coder bootstrap."
    echo "See tests/e2e/fixtures/coder.md for the manual bootstrap procedure."
    exit 0
fi

if ! curl -fsS -o /dev/null --max-time 5 "${CODER_INTERNAL_URL}/healthz" 2>/dev/null; then
    echo "Coder is not reachable at ${CODER_INTERNAL_URL}; skipping bootstrap."
    echo "See tests/e2e/fixtures/coder.md for the manual bootstrap procedure."
    exit 0
fi

echo "Coder bootstrap is a documented manual step for this environment."
echo "See tests/e2e/fixtures/coder.md for the exact procedure."
exit 0
