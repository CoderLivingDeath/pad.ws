#!/usr/bin/env bash
# UC-09 — Upgrade and rollback (dry-run / no-stack path).
#
# Validates release manifest handling, digest persistence and backup-state
# selection without recreating services or touching production data.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DEPLOY_SCRIPT="$REPO_ROOT/scripts/deploy.sh"

cd "$REPO_ROOT"

echo "=== UC-09 upgrade and rollback checks ==="

tmp_env="$(mktemp -t uc09-XXXXXX.env)"
tmp_state="$(mktemp -d -t uc09-state-XXXXXX)"
tmp_release="$(mktemp -d -t uc09-release-XXXXXX)"
tmp_backup="$(mktemp -d -t uc09-backup-XXXXXX)"
trap 'rm -f "$tmp_env"; rm -rf "$tmp_state" "$tmp_release" "$tmp_backup"' EXIT

cat > "$tmp_env" <<'EOF'
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
ADMIN_ALLOWLIST=203.0.113.0/24
TRUSTED_PROXY_IPS=172.28.0.2
PAD_ALLOWED_ROLES=pad-user
API_WORKERS=1
SESSION_COOKIE_NAME=session_id
STATIC_DIR=/app/frontend/dist
ASSETS_DIR=/app/frontend/dist/assets
BACKUP_RETENTION_DAYS=30
CADDY_IMAGE=caddy:2-alpine@sha256:0000000000000000000000000000000000000000000000000000000000000000
POSTGRES_IMAGE=postgres:16@sha256:63e83b5a3dc36a917dccb76fe1bd2ac51f1ec9c1deb47ff20d4f04233bf6eae9
REDIS_IMAGE=redis:7.2-alpine@sha256:a2c8f9d7c49c74ebd2945e3798c71606545c5f0d90d03e9ec4a2bb8d4f56df36
KEYCLOAK_IMAGE=quay.io/keycloak/keycloak:25.0@sha256:82c5b7a110456dbd42b86ea572e728878549954cc8bd03cd65410d75328095d2
CODER_IMAGE=ghcr.io/coder/coder:latest@sha256:77500de63a62f733bb1fbbf79da85e8ad4d6ca582e964f5d6021f46f6dc7fc29
PAD_IMAGE=ghcr.io/pad-ws/pad.ws:main@sha256:0000000000000000000000000000000000000000000000000000000000000000
EOF

old_digest_caddy="caddy:2-alpine@sha256:0000000000000000000000000000000000000000000000000000000000000000"
new_digest_caddy="caddy:2-alpine@sha256:1111111111111111111111111111111111111111111111111111111111111111"
new_digest_postgres="postgres:16@sha256:2222222222222222222222222222222222222222222222222222222222222222"

# Current release manifest.
mkdir -p "$tmp_state"
cat > "$tmp_state/current.json" <<EOF
{
  "version": "0.1.0",
  "images": {
    "CADDY_IMAGE": "${old_digest_caddy}"
  }
}
EOF

# New release manifest.
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

# ---------------------------------------------------------------------------
# 1. apply_release_images persists the new digests into .env.
# ---------------------------------------------------------------------------
(
    ENV_FILE="$tmp_env"
    STATE_DIR="$tmp_state"
    RELEASES_DIR="$tmp_release"
    PROFILE=production
    source "$DEPLOY_SCRIPT"
    apply_release_images "$tmp_release/0.2.0.json"
)

if ! grep -q "^CADDY_IMAGE=${new_digest_caddy}" "$tmp_env"; then
    echo "FAIL: CADDY_IMAGE was not updated" >&2
    exit 1
fi
if ! grep -q "^POSTGRES_IMAGE=${new_digest_postgres}" "$tmp_env"; then
    echo "FAIL: POSTGRES_IMAGE was not updated" >&2
    exit 1
fi
echo "Upgrade digests persisted to .env OK"

# ---------------------------------------------------------------------------
# 2. save_previous_release + record_last_backup record the old backup set.
# ---------------------------------------------------------------------------
old_pad="$tmp_backup/pad_20260101_000000.dump.gz"
new_pad="$tmp_backup/pad_20261201_000000.dump.gz"
old_keycloak="$tmp_backup/keycloak_20260101_000000.dump.gz"
new_keycloak="$tmp_backup/keycloak_20261201_000000.dump.gz"
old_coder="$tmp_backup/coder_20260101_000000.dump.gz"
new_coder="$tmp_backup/coder_20261201_000000.dump.gz"

for f in "$old_pad" "$old_keycloak" "$old_coder"; do
    echo "-- old" | gzip > "$f"
done

(
    ENV_FILE="$tmp_env"
    STATE_DIR="$tmp_state"
    BACKUP_DIR="$tmp_backup"
    PROFILE=production
    source "$DEPLOY_SCRIPT"
    save_previous_release
    record_last_backup
)

for f in "$new_pad" "$new_keycloak" "$new_coder"; do
    echo "-- new" | gzip > "$f"
done

if ! python3 - "$tmp_state/previous.json" "$old_pad" "$old_keycloak" "$old_coder" <<'PY'
import sys, json, os
state = json.load(open(sys.argv[1]))
expected = {
    'pad': os.path.basename(sys.argv[2]),
    'keycloak': os.path.basename(sys.argv[3]),
    'coder': os.path.basename(sys.argv[4]),
}
actual = state.get('backup', {}).get('dumps', {})
if actual != expected:
    print(f"expected {expected}, got {actual}", file=sys.stderr)
    sys.exit(1)
PY
then
    echo "FAIL: previous.json does not contain the expected old backup set" >&2
    exit 1
fi
echo "Rollback backup-state selection OK"

# ---------------------------------------------------------------------------
# 3. Upgrade with a missing manifest fails cleanly.
# ---------------------------------------------------------------------------
if ENV_FILE="$tmp_env" STATE_DIR="$tmp_state" RELEASES_DIR="$tmp_release" bash "$DEPLOY_SCRIPT" upgrade 9.9.9 >/dev/null 2>&1; then
    echo "FAIL: upgrade with missing manifest succeeded" >&2
    exit 1
fi
echo "Missing manifest upgrade rejection OK"

# ---------------------------------------------------------------------------
# 4. Rollback with no previous release recorded fails cleanly.
# ---------------------------------------------------------------------------
empty_state="$(mktemp -d -t uc09-empty-state-XXXXXX)"
trap 'rm -f "$tmp_env"; rm -rf "$tmp_state" "$tmp_release" "$tmp_backup" "$empty_state"' EXIT

if ENV_FILE="$tmp_env" STATE_DIR="$empty_state" bash "$DEPLOY_SCRIPT" rollback >/dev/null 2>&1; then
    echo "FAIL: rollback with no previous state succeeded" >&2
    rm -rf "$empty_state"
    exit 1
fi
rm -rf "$empty_state"
echo "Rollback-without-previous-state rejection OK"

echo "=== UC-09 checks passed ==="
