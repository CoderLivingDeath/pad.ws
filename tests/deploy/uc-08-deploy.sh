#!/usr/bin/env bash
# UC-08 — One-command deployment (dry-run / no-stack path).
#
# Validates configuration resolution, preflight success/failure and the deploy
# script surface without starting containers or touching production data.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DEPLOY_SCRIPT="$REPO_ROOT/scripts/deploy.sh"

cd "$REPO_ROOT"

echo "=== UC-08 one-command deployment checks ==="

# ---------------------------------------------------------------------------
# 1. Help documents every operator subcommand.
# ---------------------------------------------------------------------------
for command in up down destroy status logs backup restore rotate-key upgrade rollback; do
    if ! bash "$DEPLOY_SCRIPT" --help 2>&1 | grep -qw "$command"; then
        echo "FAIL: deploy.sh --help does not document '$command'" >&2
        exit 1
    fi
done
echo "Deploy help documents all commands OK"

# ---------------------------------------------------------------------------
# 2. Local profile dry-run succeeds with generated secrets.
# ---------------------------------------------------------------------------
tmp_local_env="$(mktemp -t uc08-local-XXXXXX.env)"
tmp_state="$(mktemp -d -t uc08-state-XXXXXX)"
trap 'rm -f "$tmp_local_env"; rm -rf "$tmp_state"' EXIT

if ! ENV_FILE="$tmp_local_env" STATE_DIR="$tmp_state" bash "$DEPLOY_SCRIPT" up --profile local \
    --set CODER_TEMPLATE_ID=00000000-0000-0000-0000-000000000001 \
    --set CODER_DEFAULT_ORGANIZATION=00000000-0000-0000-0000-000000000002 \
    --dry-run >/dev/null 2>&1; then
    echo "FAIL: local profile dry-run failed" >&2
    exit 1
fi
echo "Local dry-run OK"

# ---------------------------------------------------------------------------
# 3. Production profile dry-run succeeds with a valid allowlist.
# ---------------------------------------------------------------------------
tmp_prod_env="$(mktemp -t uc08-prod-XXXXXX.env)"
trap 'rm -f "$tmp_local_env" "$tmp_prod_env"; rm -rf "$tmp_state"' EXIT

cat > "$tmp_prod_env" <<'EOF'
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
CODER_TEMPLATE_ID=00000000-0000-0000-0000-000000000001
CODER_DEFAULT_ORGANIZATION=00000000-0000-0000-0000-000000000002
CODER_WORKSPACE_NAME=ubuntu
CODER_DB=coder
CODER_DB_PASSWORD_URLENCODED=secret
DOCKER_GROUP_ID=999
ADMIN_ALLOWLIST=203.0.113.0/24
TRUSTED_PROXY_IPS=172.28.0.2
PAD_ALLOWED_ROLES=pad-user
API_WORKERS=1
SESSION_COOKIE_NAME=session_id
STATIC_DIR=/app/frontend/dist
ASSETS_DIR=/app/frontend/dist/assets
BACKUP_RETENTION_DAYS=30
CADDY_IMAGE=caddy:2-alpine@sha256:003a97808e781aa9f7e75cc2f43d34d461099031faf5e20faefb9f61126836f0
POSTGRES_IMAGE=postgres:16@sha256:63e83b5a3dc36a917dccb76fe1bd2ac51f1ec9c1deb47ff20d4f04233bf6eae9
REDIS_IMAGE=redis:7.2-alpine@sha256:a2c8f9d7c49c74ebd2945e3798c71606545c5f0d90d03e9ec4a2bb8d4f56df36
KEYCLOAK_IMAGE=quay.io/keycloak/keycloak:25.0@sha256:82c5b7a110456dbd42b86ea572e728878549954cc8bd03cd65410d75328095d2
CODER_IMAGE=ghcr.io/coder/coder:latest@sha256:77500de63a62f733bb1fbbf79da85e8ad4d6ca582e964f5d6021f46f6dc7fc29
PAD_IMAGE=ghcr.io/pad-ws/pad.ws:main@sha256:0000000000000000000000000000000000000000000000000000000000000000
EOF

if ! ENV_FILE="$tmp_prod_env" STATE_DIR="$tmp_state" bash "$DEPLOY_SCRIPT" up --profile production --domain example.com --allowlist "203.0.113.0/24" --dry-run >/dev/null 2>&1; then
    echo "FAIL: production dry-run with valid allowlist failed" >&2
    exit 1
fi
echo "Production valid dry-run OK"

# ---------------------------------------------------------------------------
# 4. Production with a placeholder fails before compose starts.
# ---------------------------------------------------------------------------
if ENV_FILE="$tmp_prod_env" STATE_DIR="$tmp_state" bash "$DEPLOY_SCRIPT" up --profile production --domain example.com --allowlist "203.0.113.0/24" \
    --set CODER_TEMPLATE_ID='__CHANGE_ME__' \
    --dry-run >/dev/null 2>&1; then
    echo "FAIL: production dry-run accepted a placeholder value" >&2
    exit 1
fi
echo "Production placeholder rejection OK"

# ---------------------------------------------------------------------------
# 5. Production open allowlist is rejected.
# ---------------------------------------------------------------------------
if ENV_FILE="$tmp_prod_env" STATE_DIR="$tmp_state" bash "$DEPLOY_SCRIPT" up --profile production --domain example.com --allowlist "0.0.0.0/0 ::/0" \
    --dry-run >/dev/null 2>&1; then
    echo "FAIL: production open allowlist was accepted" >&2
    exit 1
fi
echo "Production open allowlist rejection OK"

# ---------------------------------------------------------------------------
# 6. Topology invariants are enforced in the production compose file.
# ---------------------------------------------------------------------------
if ! bash "$REPO_ROOT/tests/deploy/run-checks.sh" >/dev/null 2>&1; then
    echo "FAIL: deployment invariant checks failed" >&2
    exit 1
fi
echo "Deployment invariant checks OK"

echo "=== UC-08 checks passed ==="
