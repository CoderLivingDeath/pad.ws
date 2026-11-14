#!/usr/bin/env bash
set -euo pipefail

# Verify that apply_release_images persists manifest digests into .env and that
# docker compose config resolves them.

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DEPLOY_SCRIPT="$REPO_ROOT/scripts/deploy.sh"
RELEASES_DIR="$REPO_ROOT/deploy/releases"

cd "$REPO_ROOT"

echo "=== Upgrade/rollback image digest tests ==="

# Create a production-like .env with a stale image digest set.
tmp_env="$(mktemp -t upgrade-images-XXXXXX.env)"
tmp_state="$(mktemp -d -t upgrade-state-XXXXXX)"
tmp_release="$(mktemp -d -t upgrade-releases-XXXXXX)"
trap 'rm -f "$tmp_env"; rm -rf "$tmp_state" "$tmp_release"' EXIT

old_digest_caddy="caddy:2-alpine@sha256:0000000000000000000000000000000000000000000000000000000000000000"
new_digest_caddy="caddy:2-alpine@sha256:1111111111111111111111111111111111111111111111111111111111111111"
new_digest_postgres="postgres:16@sha256:2222222222222222222222222222222222222222222222222222222222222222"

cat > "$tmp_env" <<EOF
PROFILE=production
PAD_DOMAIN=pad.example.com
AUTH_DOMAIN=auth.example.com
CODER_DOMAIN=coder.example.com
COOKIE_DOMAIN=.example.com
ACME_EMAIL=ops@example.com
CADDYFILE=deploy/Caddyfile
OIDC_SERVER_URL=https://auth.example.com
REDIRECT_URI=https://pad.example.com/api/auth/callback
FRONTEND_URL=https://pad.example.com
OIDC_INTERNAL_URL=http://keycloak:8080
CODER_URL=https://coder.example.com
CODER_INTERNAL_URL=http://coder:7080
OIDC_REALM=pad
OIDC_CLIENT_ID=pad
OIDC_CLIENT_SECRET=secret
POSTGRES_USER=pad
POSTGRES_PASSWORD=secret
POSTGRES_DB=pad
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
REDIS_PASSWORD=secret
REDIS_HOST=redis
REDIS_PORT=6379
KEYCLOAK_ADMIN=admin
KEYCLOAK_ADMIN_PASSWORD=secret
KEYCLOAK_DB=keycloak
CODER_API_KEY=secret
CODER_API_KEY_CREATED_AT=2026-01-01T00:00:00Z
CODER_TEMPLATE_ID=00000000-0000-0000-0000-000000000001
CODER_DEFAULT_ORGANIZATION=00000000-0000-0000-0000-000000000002
CODER_WORKSPACE_NAME=ubuntu
CODER_DB=coder
CODER_DB_PASSWORD_URLENCODED=secret
DOCKER_GROUP_ID=999
ADMIN_ALLOWLIST="203.0.113.0/24"
TRUSTED_PROXY_IPS=172.28.0.2
PAD_ALLOWED_ROLES=pad-user
API_WORKERS=1
SESSION_COOKIE_NAME=session_id
STATIC_DIR=/app/frontend/dist
ASSETS_DIR=/app/frontend/dist/assets
BACKUP_RETENTION_DAYS=30
CADDY_IMAGE=${old_digest_caddy}
POSTGRES_IMAGE=postgres:16@sha256:63e83b5a3dc36a917dccb76fe1bd2ac51f1ec9c1deb47ff20d4f04233bf6eae9
REDIS_IMAGE=redis:7.2-alpine@sha256:a2c8f9d7c49c74ebd2945e3798c71606545c5f0d90d03e9ec4a2bb8d4f56df36
KEYCLOAK_IMAGE=quay.io/keycloak/keycloak:25.0@sha256:82c5b7a110456dbd42b86ea572e728878549954cc8bd03cd65410d75328095d2
CODER_IMAGE=ghcr.io/coder/coder:latest@sha256:77500de63a62f733bb1fbbf79da85e8ad4d6ca582e964f5d6021f46f6dc7fc29
PAD_IMAGE=ghcr.io/pad-ws/pad.ws:main@sha256:0000000000000000000000000000000000000000000000000000000000000000
EOF

# Create a release manifest with new digests.
cat > "$tmp_release/0.2.0.json" <<EOF
{
  "version": "0.2.0",
  "images": {
    "CADDY_IMAGE": "${new_digest_caddy}",
    "POSTGRES_IMAGE": "${new_digest_postgres}",
    "REDIS_IMAGE": "redis:7.2-alpine@sha256:a2c8f9d7c49c74ebd2945e3798c71606545c5f0d90d03e9ec4a2bb8d4f56df36",
    "KEYCLOAK_IMAGE": "quay.io/keycloak/keycloak:25.0@sha256:82c5b7a110456dbd42b86ea572e728878549954cc8bd03cd65410d75328095d2",
    "CODER_IMAGE": "ghcr.io/coder/coder:latest@sha256:77500de63a62f733bb1fbbf79da85e8ad4d6ca582e964f5d6021f46f6dc7fc29"
  }
}
EOF

# Source deploy.sh and apply the new release images.
(
    ENV_FILE="$tmp_env"
    STATE_DIR="$tmp_state"
    RELEASES_DIR="$tmp_release"
    PROFILE=production
    source "$DEPLOY_SCRIPT"
    apply_release_images "$tmp_release/0.2.0.json"
)

# Verify .env was updated.
if ! grep -q "^CADDY_IMAGE=${new_digest_caddy}" "$tmp_env"; then
    echo "FAIL: CADDY_IMAGE was not updated in .env" >&2
    exit 1
fi
if ! grep -q "^POSTGRES_IMAGE=${new_digest_postgres}" "$tmp_env"; then
    echo "FAIL: POSTGRES_IMAGE was not updated in .env" >&2
    exit 1
fi

# Verify docker compose config resolves the new digests.
resolved_caddy="$(docker compose -f "$REPO_ROOT/docker-compose.prod.yml" --env-file "$tmp_env" config | \
    python3 -c "import sys, yaml; d=yaml.safe_load(sys.stdin); print(d['services']['caddy']['image'])")"
if [[ "$resolved_caddy" != "$new_digest_caddy" ]]; then
    echo "FAIL: compose config resolved caddy image ${resolved_caddy}, expected ${new_digest_caddy}" >&2
    exit 1
fi

resolved_postgres="$(docker compose -f "$REPO_ROOT/docker-compose.prod.yml" --env-file "$tmp_env" config | \
    python3 -c "import sys, yaml; d=yaml.safe_load(sys.stdin); print(d['services']['postgres']['image'])")"
if [[ "$resolved_postgres" != "$new_digest_postgres" ]]; then
    echo "FAIL: compose config resolved postgres image ${resolved_postgres}, expected ${new_digest_postgres}" >&2
    exit 1
fi

echo "Manifest digests persisted to .env OK"
echo "Compose config resolves manifest digests OK"
echo "=== Upgrade/rollback image digest tests passed ==="
