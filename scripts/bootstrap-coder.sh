#!/usr/bin/env bash
set -euo pipefail

# Idempotent Coder bootstrap.
#
# Usage: scripts/bootstrap-coder.sh
#
# - Discovers the default organization and writes CODER_DEFAULT_ORGANIZATION.
# - Ensures the 'docker' template exists and writes CODER_TEMPLATE_ID.
# - Verifies the configured CODER_API_KEY and records CODER_API_KEY_CREATED_AT
#   if it is missing.
# - Safe to rerun; never deletes existing data.
#
# Coder's first owner account is created by the first OIDC login, which remains
# a manual operator step. Run deploy.sh again after that login to complete
# bootstrap.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT_DIR/.env}"
COMPOSE_FILE="${COMPOSE_FILE:-$ROOT_DIR/docker-compose.prod.yml}"
CODER_TEMPLATE_DIR="${CODER_TEMPLATE_DIR:-$ROOT_DIR/deploy/coder/template}"

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
CODER_API_KEY="${CODER_API_KEY:-}"

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

wait_for_coder() {
    echo "Waiting for Coder API..."
    for _ in $(seq 1 60); do
        if curl -fsS --max-time 5 "${CODER_INTERNAL_URL}/healthz" >/dev/null 2>&1; then
            return 0
        fi
        sleep 2
    done
    echo "ERROR: Coder did not become ready" >&2
    return 1
}

update_env() {
    local key="$1" value="$2"
    if grep -qE "^${key}=" "$ENV_FILE"; then
        sed -i "s|^${key}=.*|${key}=${value}|" "$ENV_FILE"
    else
        echo "${key}=${value}" >> "$ENV_FILE"
    fi
}

wait_for_coder

# Check whether Coder has any users yet (first-owner setup).
user_count_json="$(curl -fsS --max-time 10 "${CODER_INTERNAL_URL}/api/v2/users?q=&limit=1" 2>/dev/null || echo '{}')"
user_count="$(python3 - "$user_count_json" <<'PY'
import sys, json
print(json.loads(sys.argv[1]).get('count', 0))
PY
)"

if [[ "$user_count" == "0" ]]; then
    echo "Coder has no owner yet. Log in through the gateway first with the intended owner account, then rerun deploy."
    echo "  https://${CODER_DOMAIN:-coder.example.com}"
    exit 0
fi

# If no API key is configured, instruct the operator to create one.
if [[ -z "$CODER_API_KEY" ]]; then
    echo "CODER_API_KEY is not set. Create a provisioner API key in the Coder UI and add it to .env, then rerun deploy."
    exit 0
fi

echo "Verifying CODER_API_KEY..."
if ! curl_json GET "${CODER_INTERNAL_URL}/api/v2/users/me" "$CODER_API_KEY" >/dev/null 2>&1; then
    echo "ERROR: CODER_API_KEY is invalid or expired" >&2
    exit 1
fi

# Record created-at if missing (assume it is current for pre-existing keys).
if [[ -z "${CODER_API_KEY_CREATED_AT:-}" ]]; then
    update_env CODER_API_KEY_CREATED_AT "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
fi

# Discover default organization.
echo "Discovering default organization..."
org_json="$(curl_json GET "${CODER_INTERNAL_URL}/api/v2/organizations" "$CODER_API_KEY")"
org_id="$(python3 - "$org_json" <<'PY'
import sys, json
orgs = json.loads(sys.argv[1])
print(orgs[0]['id'] if orgs else '')
PY
)"
if [[ -z "$org_id" ]]; then
    echo "ERROR: no Coder organization found" >&2
    exit 1
fi
if [[ "${CODER_DEFAULT_ORGANIZATION:-}" != "$org_id" ]]; then
    update_env CODER_DEFAULT_ORGANIZATION "$org_id"
    echo "Set CODER_DEFAULT_ORGANIZATION=$org_id"
fi

# Discover or create the docker template.
echo "Discovering templates..."
template_json="$(curl_json GET "${CODER_INTERNAL_URL}/api/v2/templates" "$CODER_API_KEY")"
template_id="$(python3 - "$template_json" <<'PY'
import sys, json
templates = json.loads(sys.argv[1]).get('templates', [])
for t in templates:
    if t.get('name') == 'docker':
        print(t.get('id', ''))
        break
PY
)"

if [[ -z "$template_id" ]]; then
    echo "No 'docker' template found; attempting to create from ${CODER_TEMPLATE_DIR}..."
    # Create a tar of the template directory and use the Coder CLI inside the
    # running coder container to import it.
    tmp_tar="$(mktemp -t coder-template.XXXXXX.tar.gz)"
    trap 'rm -f "$tmp_tar"' EXIT
    tar czf "$tmp_tar" -C "$CODER_TEMPLATE_DIR" .
    docker cp "$tmp_tar" coder:/tmp/template.tar.gz >/dev/null
    if docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" exec -T coder \
        sh -c "mkdir -p /tmp/coder-template && tar xzf /tmp/template.tar.gz -C /tmp/coder-template && coder templates create docker -O ${org_id} -y -d /tmp/coder-template" 2>&1; then
        template_json="$(curl_json GET "${CODER_INTERNAL_URL}/api/v2/templates" "$CODER_API_KEY")"
        template_id="$(python3 - "$template_json" <<'PY'
import sys, json
templates = json.loads(sys.argv[1]).get('templates', [])
for t in templates:
    if t.get('name') == 'docker':
        print(t.get('id', ''))
        break
PY
)"
    else
        echo "WARN: could not create the docker template automatically; create it in the Coder UI and set CODER_TEMPLATE_ID."
    fi
fi

if [[ -n "$template_id" ]] && [[ "${CODER_TEMPLATE_ID:-}" != "$template_id" ]]; then
    update_env CODER_TEMPLATE_ID "$template_id"
    echo "Set CODER_TEMPLATE_ID=$template_id"
fi

# Ensure admin workspace exists.
if [[ -n "${CODER_ADMIN_USERNAME:-}" ]]; then
    echo "Ensuring admin workspace exists for ${CODER_ADMIN_USERNAME}..."
    workspace_json="$(curl_json GET "${CODER_INTERNAL_URL}/api/v2/users/${CODER_ADMIN_USERNAME}/workspace/${CODER_WORKSPACE_NAME:-ubuntu}" "$CODER_API_KEY" 2>/dev/null || echo '{}')"
    if [[ -z "$(python3 - "$workspace_json" <<'PY'
import sys, json
ws = json.loads(sys.argv[1])
print(ws.get('id', ''))
PY
)" ]]; then
        if [[ -n "$template_id" ]]; then
            curl_json POST "${CODER_INTERNAL_URL}/api/v2/workspaces" "$CODER_API_KEY" \
                "{\"name\":\"${CODER_WORKSPACE_NAME:-ubuntu}\",\"template_id\":\"${template_id}\",\"user\":\"${CODER_ADMIN_USERNAME}\"}" >/dev/null
            echo "Created admin workspace."
        fi
    else
        echo "Admin workspace already exists."
    fi
fi

echo "Coder bootstrap complete."
