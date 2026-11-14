#!/usr/bin/env bash
set -euo pipefail

# Rotate the Coder API key used by Pad.
#
# Usage:
#   ./scripts/rotate-coder-key.sh
#
# The script:
#   1. Creates a new Coder API key using the current key.
#   2. Updates .env with the new key and CODER_API_KEY_CREATED_AT.
#   3. Restarts Pad so it picks up the new key.
#   4. Revokes the old key.
#   5. Verifies the new key works against Coder and (optionally) Pad workspace state.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT_DIR/.env}"
COMPOSE_FILE="${COMPOSE_FILE:-$ROOT_DIR/docker-compose.prod.yml}"

cd "$ROOT_DIR"

if [[ ! -f "$ENV_FILE" ]]; then
    echo "ERROR: $ENV_FILE not found" >&2
    exit 1
fi

set -a
# shellcheck source=/dev/null
source "$ENV_FILE"
set +a

CODER_INTERNAL_URL="${CODER_INTERNAL_URL:-http://coder:7080}"
PAD_BASE_URL="${PAD_BASE_URL:-https://${PAD_DOMAIN:-}}"
KEY_NAME="pad-deploy-$(date +%Y%m%d-%H%M%S)"

curl_json() {
    python3 - "$@" <<'PY'
import sys, json, urllib.request, urllib.error
method, url, token = sys.argv[1], sys.argv[2], sys.argv[3]
data = sys.argv[4] if len(sys.argv) > 4 else None
headers = {
    'Accept': 'application/json',
    'Coder-Session-Token': token,
}
if data:
    headers['Content-Type'] = 'application/json'
req = urllib.request.Request(url, method=method, data=data.encode() if data else None, headers=headers)
try:
    with urllib.request.urlopen(req, timeout=30) as resp:
        print(resp.read().decode())
except urllib.error.HTTPError as e:
    print(e.read().decode(), file=sys.stderr)
    sys.exit(1)
PY
}

if [[ -z "${CODER_API_KEY:-}" ]]; then
    echo "ERROR: CODER_API_KEY is not set in $ENV_FILE" >&2
    exit 1
fi

echo "Listing existing Coder API keys..."
old_keys_json="$(curl_json GET "${CODER_INTERNAL_URL}/api/v2/users/me/keys" "$CODER_API_KEY" 2>/dev/null || echo '[]')"
old_key_id=""
if [[ -n "$old_keys_json" ]]; then
    old_key_id="$(python3 - "$old_keys_json" "$KEY_NAME" <<'PY'
import sys, json
keys = json.loads(sys.argv[1])
for k in keys:
    if k.get('token_name', '').startswith('pad-deploy-'):
        print(k.get('id', ''))
        break
PY
)"
fi

echo "Creating new Coder API key: $KEY_NAME"
new_key_json="$(curl_json POST "${CODER_INTERNAL_URL}/api/v2/users/me/keys" "$CODER_API_KEY" "{\"token_name\":\"$KEY_NAME\",\"scope\":\"all\"}")"
new_key="$(python3 - "$new_key_json" <<'PY'
import sys, json
print(json.loads(sys.argv[1]).get('key', ''))
PY
)"
new_key_id="$(python3 - "$new_key_json" <<'PY'
import sys, json
print(json.loads(sys.argv[1]).get('id', ''))
PY
)"

if [[ -z "$new_key" ]]; then
    echo "ERROR: failed to create new Coder API key" >&2
    exit 1
fi

echo "Verifying new key against Coder /api/v2/users/me..."
if ! curl_json GET "${CODER_INTERNAL_URL}/api/v2/users/me" "$new_key" >/dev/null; then
    echo "ERROR: new key is not accepted by Coder" >&2
    exit 1
fi

echo "Updating $ENV_FILE with new key..."
# Update CODER_API_KEY without changing other values; never print the key.
timestamp="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
if grep -qE '^CODER_API_KEY=' "$ENV_FILE"; then
    sed -i "s/^CODER_API_KEY=.*/CODER_API_KEY=${new_key}/" "$ENV_FILE"
else
    echo "CODER_API_KEY=${new_key}" >> "$ENV_FILE"
fi
if grep -qE '^CODER_API_KEY_CREATED_AT=' "$ENV_FILE"; then
    sed -i "s/^CODER_API_KEY_CREATED_AT=.*/CODER_API_KEY_CREATED_AT=${timestamp}/" "$ENV_FILE"
else
    echo "CODER_API_KEY_CREATED_AT=${timestamp}" >> "$ENV_FILE"
fi
chmod 600 "$ENV_FILE"

echo "Restarting Pad to pick up the new key..."
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" restart pad >/dev/null

# Wait briefly for Pad to become ready.
for _ in $(seq 1 30); do
    if docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" exec -T pad curl -fsS http://localhost:8000/ >/dev/null 2>&1; then
        break
    fi
    sleep 1
done

# ---------------------------------------------------------------------------
# Optional Pad workspace-state verification.
# Set PAD_SESSION_COOKIE to a valid session_id cookie value to run it.
# ---------------------------------------------------------------------------
if [[ -n "${PAD_SESSION_COOKIE:-}" ]]; then
    echo "Verifying Pad /api/workspace/state..."
    if curl -fsS --max-time 10 -b "session_id=${PAD_SESSION_COOKIE}" \
        "${PAD_BASE_URL}/api/workspace/state" >/dev/null 2>&1; then
        echo "Pad /api/workspace/state returned 200"
    else
        echo "WARN: Pad /api/workspace/state did not return 200 (session may have expired)" >&2
    fi
else
    echo "Skipping Pad /api/workspace/state verification (set PAD_SESSION_COOKIE to enable)"
fi

# ---------------------------------------------------------------------------
# Revoke the old key using the new key.
# ---------------------------------------------------------------------------
if [[ -n "$old_key_id" ]]; then
    echo "Revoking old Coder API key..."
    curl_json DELETE "${CODER_INTERNAL_URL}/api/v2/users/me/keys/${old_key_id}" "$new_key" >/dev/null || true
fi

echo "Coder key rotation complete. New key created at ${timestamp}."
