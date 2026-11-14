#!/usr/bin/env bash
set -euo pipefail

# Verify that resolve_config merges into .env without dropping operator-supplied
# unknown keys.

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DEPLOY_SCRIPT="$REPO_ROOT/scripts/deploy.sh"

cd "$REPO_ROOT"

echo "=== .env merge tests ==="

# Create a .env with an unknown operator key.
tmp_env="$(mktemp -t merge-test-XXXXXX.env)"
trap 'rm -f "$tmp_env"' EXIT

cat > "$tmp_env" <<'EOF'
PROFILE=local
PAD_DOMAIN=pad.pad.test
AUTH_DOMAIN=auth.pad.test
CODER_DOMAIN=coder.pad.test
COOKIE_DOMAIN=.pad.test
ACME_EMAIL=local@pad.test
CADDYFILE=deploy/Caddyfile.local
OIDC_SERVER_URL=https://auth.pad.test
REDIRECT_URI=https://pad.pad.test/api/auth/callback
FRONTEND_URL=https://pad.pad.test
OIDC_INTERNAL_URL=http://keycloak:8080
CODER_URL=https://coder.pad.test
CODER_INTERNAL_URL=http://coder:7080
OIDC_REALM=pad
OIDC_CLIENT_ID=pad
OIDC_CLIENT_SECRET=pad-test-secret
POSTGRES_USER=admin
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
CODER_TEMPLATE_ID=00000000-0000-0000-0000-000000000001
CODER_DEFAULT_ORGANIZATION=00000000-0000-0000-0000-000000000002
CODER_WORKSPACE_NAME=ubuntu
CODER_DB=coder
CODER_DB_PASSWORD_URLENCODED=secret
DOCKER_GROUP_ID=999
ADMIN_ALLOWLIST="0.0.0.0/0 ::/0"
TRUSTED_PROXY_IPS=172.28.0.2
PAD_ALLOWED_ROLES=pad-user
API_WORKERS=1
SESSION_COOKIE_NAME=session_id
STATIC_DIR=/app/frontend/dist
ASSETS_DIR=/app/frontend/dist/assets
BACKUP_RETENTION_DAYS=7
CADDY_IMAGE=caddy:2-alpine@sha256:003a97808e781aa9f7e75cc2f43d34d461099031faf5e20faefb9f61126836f0
POSTGRES_IMAGE=postgres:16@sha256:63e83b5a3dc36a917dccb76fe1bd2ac51f1ec9c1deb47ff20d4f04233bf6eae9
REDIS_IMAGE=redis:7.2-alpine@sha256:a2c8f9d7c49c74ebd2945e3798c71606545c5f0d90d03e9ec4a2bb8d4f56df36
KEYCLOAK_IMAGE=quay.io/keycloak/keycloak:25.0@sha256:82c5b7a110456dbd42b86ea572e728878549954cc8bd03cd65410d75328095d2
CODER_IMAGE=ghcr.io/coder/coder:latest@sha256:77500de63a62f733bb1fbbf79da85e8ad4d6ca582e964f5d6021f46f6dc7fc29
PAD_IMAGE=pad-ws:test
OPERATOR_CUSTOM_KEY=should-survive
EOF

# Source the deploy script in a sub-shell with our test .env.
(
    ENV_FILE="$tmp_env"
    PROFILE=local
    source "$DEPLOY_SCRIPT"
    resolve_config >/dev/null 2>&1
)

if ! grep -q '^OPERATOR_CUSTOM_KEY=should-survive' "$tmp_env"; then
    echo "FAIL: unknown operator key was dropped from .env" >&2
    exit 1
fi

# Also verify a known key was updated (POSTGRES_PASSWORD gets regenerated if
# it looks like a placeholder, but our value is not a placeholder so it stays).
if ! grep -q '^POSTGRES_PASSWORD=secret$' "$tmp_env"; then
    echo "FAIL: known key value was not preserved" >&2
    exit 1
fi

echo "Unknown key preserved OK"
echo "Known key preserved OK"
echo "=== .env merge tests passed ==="
