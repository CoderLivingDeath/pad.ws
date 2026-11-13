#!/usr/bin/env bash
set -euo pipefail

# Run integration tests through Caddy on https://pad.pad.test.
# The test container shares Caddy's network namespace, so the three public
# hostnames resolve to 127.0.0.1 and the Caddy internal CA can be trusted.
# Usage: scripts/test-integration.sh [pytest args...]

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT_DIR}/.env.test"
COMPOSE="docker compose -f ${ROOT_DIR}/docker-compose.prod.yml -f ${ROOT_DIR}/compose.test.yml --env-file ${ENV_FILE}"

cd "${ROOT_DIR}"

if [[ ! -f "${ENV_FILE}" ]]; then
    echo "Error: ${ENV_FILE} is missing; run scripts/test-env.sh up first" >&2
    exit 1
fi

caddy_container="$(${COMPOSE} ps -q caddy 2>/dev/null || true)"
if [[ -z "${caddy_container}" ]]; then
    echo "Error: the caddy service is not running; run scripts/test-env.sh up first" >&2
    exit 1
fi

network_name="$(docker inspect -f '{{range $k,$v := .NetworkSettings.Networks}}{{$k}}{{end}}' "${caddy_container}")"
caddy_ip="$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "${caddy_container}")"
if [[ -z "${network_name}" || -z "${caddy_ip}" ]]; then
    echo "Error: could not determine the Caddy network address" >&2
    exit 1
fi

if [[ ! -f "${ROOT_DIR}/caddy-root.crt" ]]; then
    echo "Error: caddy-root.crt is missing; run scripts/test-env.sh up first" >&2
    exit 1
fi

exec docker run --rm \
    --network "${network_name}" \
    --add-host "pad.pad.test:${caddy_ip}" \
    --add-host "auth.pad.test:${caddy_ip}" \
    --add-host "coder.pad.test:${caddy_ip}" \
    --env-file "${ENV_FILE}" \
    -e PAD_BASE_URL=https://pad.pad.test \
    -e AUTH_BASE_URL=https://auth.pad.test \
    -e CODER_BASE_URL=https://coder.pad.test \
    -e OIDC_INTERNAL_URL=http://keycloak:8080 \
    -e REDIS_HOST=redis \
    -e SSL_CERT_FILE=/app/caddy-root.crt \
    -v "${ROOT_DIR}:/app" \
    -w /app \
    python:3.11-slim \
    sh -c "pip install -q -r requirements-dev.txt -r src/backend/requirements.txt && pytest tests/integration -m integration -v $*"
