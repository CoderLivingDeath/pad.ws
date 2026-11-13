#!/usr/bin/env bash
set -euo pipefail

# Run integration tests inside the compose network.
# The host cannot reach pad:8000 or redis:6379 because they are not published.
# Usage: scripts/test-integration.sh [pytest args...]

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT_DIR}/.env.test"
COMPOSE="docker compose -f ${ROOT_DIR}/docker-compose.prod.yml -f ${ROOT_DIR}/compose.test.yml --env-file ${ENV_FILE}"

cd "${ROOT_DIR}"

if [[ ! -f "${ENV_FILE}" ]]; then
    echo "Error: ${ENV_FILE} is missing; run scripts/test-env.sh up first" >&2
    exit 1
fi

pad_container="$(${COMPOSE} ps -q pad 2>/dev/null || true)"
if [[ -z "${pad_container}" ]]; then
    echo "Error: the pad service is not running; run scripts/test-env.sh up first" >&2
    exit 1
fi

# Share the Pad container network namespace so `redis`, `keycloak` and
# `localhost:8000` resolve exactly as they do inside the stack.
exec docker run --rm \
    --network "container:${pad_container}" \
    --env-file "${ENV_FILE}" \
    -e PAD_BASE_URL=http://localhost:8000 \
    -e OIDC_INTERNAL_URL=http://keycloak:8080 \
    -e REDIS_HOST=redis \
    -v "${ROOT_DIR}:/app" \
    -w /app \
    python:3.11-slim \
    sh -c "pip install -q -r requirements-dev.txt -r src/backend/requirements.txt && pytest tests/integration -m integration -v $*"
