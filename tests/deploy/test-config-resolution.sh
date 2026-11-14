#!/usr/bin/env bash
set -euo pipefail

# Verify configuration precedence and preflight behavior without starting services.

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DEPLOY_SCRIPT="$REPO_ROOT/scripts/deploy.sh"

cd "$REPO_ROOT"

echo "=== Config resolution tests ==="

# 1. CLI override wins over profile default.
output="$(bash "$DEPLOY_SCRIPT" up --profile production --domain example.com --allowlist "203.0.113.0/24" \
    --set ACME_EMAIL=ops@example.com \
    --set CODER_TEMPLATE_ID=00000000-0000-0000-0000-000000000001 \
    --set CODER_DEFAULT_ORGANIZATION=00000000-0000-0000-0000-000000000002 \
    --set PAD_IMAGE=ghcr.io/pad-ws/pad.ws:main@sha256:0000000000000000000000000000000000000000000000000000000000000000 \
    --dry-run)"
if ! echo "$output" | grep -q 'PAD_DOMAIN=pad.example.com'; then
    echo "FAIL: --domain did not override PAD_DOMAIN" >&2
    exit 1
fi
if ! echo "$output" | grep -q 'Allowlist: 203.0.113.0/24'; then
    echo "FAIL: --allowlist did not override ADMIN_ALLOWLIST" >&2
    exit 1
fi
echo "CLI override wins OK"

# 2. Placeholder fails preflight before compose validation.
if bash "$DEPLOY_SCRIPT" up --profile production --domain example.com --allowlist "203.0.113.0/24" \
    --set CODER_TEMPLATE_ID='__CHANGE_ME__' \
    --dry-run >/dev/null 2>&1; then
    echo "FAIL: placeholder CODER_TEMPLATE_ID was accepted" >&2
    exit 1
fi
echo "Placeholder rejection OK"

# 3. Local profile allows open allowlist.
if ! bash "$DEPLOY_SCRIPT" up --profile local --dry-run >/dev/null 2>&1; then
    echo "FAIL: local profile with open allowlist was rejected" >&2
    exit 1
fi
echo "Local open allowlist OK"

# 4. Production open allowlist rejected.
if bash "$DEPLOY_SCRIPT" up --profile production --domain example.com --allowlist "0.0.0.0/0 ::/0" \
    --set ACME_EMAIL=ops@example.com \
    --set CODER_TEMPLATE_ID=00000000-0000-0000-0000-000000000001 \
    --set CODER_DEFAULT_ORGANIZATION=00000000-0000-0000-0000-000000000002 \
    --set PAD_IMAGE=ghcr.io/pad-ws/pad.ws:main@sha256:0000000000000000000000000000000000000000000000000000000000000000 \
    --dry-run >/dev/null 2>&1; then
    echo "FAIL: production open allowlist was accepted" >&2
    exit 1
fi
echo "Production open allowlist rejection OK"

# 5. Rerun preserves generated secrets (idempotency of resolution).
secret_before=""
if [[ -f .env ]]; then
    secret_before="$(grep '^POSTGRES_PASSWORD=' .env | cut -d= -f2)"
fi
bash "$DEPLOY_SCRIPT" up --profile local --dry-run >/dev/null 2>&1
secret_after="$(grep '^POSTGRES_PASSWORD=' .env | cut -d= -f2)"
if [[ -n "$secret_before" && "$secret_before" != "$secret_after" ]]; then
    echo "FAIL: POSTGRES_PASSWORD changed on dry-run rerun" >&2
    exit 1
fi
echo "Secret preserved on rerun OK"

echo "=== Config resolution tests passed ==="
