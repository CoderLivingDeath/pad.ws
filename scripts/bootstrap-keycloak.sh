#!/usr/bin/env bash
set -euo pipefail

# Idempotent Keycloak bootstrap.
#
# Usage: scripts/bootstrap-keycloak.sh
#
# - Imports deploy/keycloak/realm-export.json on a fresh database.
# - Reconciles the 'pad' client redirect URIs, web origins and settings.
# - Ensures realm roles 'pad-user' and 'admin' exist.
# - Sets session lifetimes (8h idle, 7d max).
# - Safe to rerun; never deletes an existing realm.

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

KEYCLOAK_ADMIN="${KEYCLOAK_ADMIN:-admin}"
KEYCLOAK_ADMIN_PASSWORD="${KEYCLOAK_ADMIN_PASSWORD:-}"
KEYCLOAK_INTERNAL_URL="${KEYCLOAK_INTERNAL_URL:-http://keycloak:8080}"
OIDC_REALM="${OIDC_REALM:-pad}"
OIDC_CLIENT_ID="${OIDC_CLIENT_ID:-pad}"
PAD_DOMAIN="${PAD_DOMAIN:-}"
AUTH_DOMAIN="${AUTH_DOMAIN:-}"
CODER_DOMAIN="${CODER_DOMAIN:-}"

if [[ -z "$KEYCLOAK_ADMIN_PASSWORD" ]]; then
    echo "ERROR: KEYCLOAK_ADMIN_PASSWORD is not set" >&2
    exit 1
fi

wait_for_keycloak() {
    echo "Waiting for Keycloak admin API..."
    for _ in $(seq 1 60); do
        if curl -fsS --max-time 5 "${KEYCLOAK_INTERNAL_URL}/realms/master" >/dev/null 2>&1; then
            return 0
        fi
        sleep 2
    done
    echo "ERROR: Keycloak did not become ready" >&2
    return 1
}

wait_for_keycloak

python3 - "$KEYCLOAK_INTERNAL_URL" "$KEYCLOAK_ADMIN" "$KEYCLOAK_ADMIN_PASSWORD" \
    "$OIDC_REALM" "$OIDC_CLIENT_ID" "$PAD_DOMAIN" "$AUTH_DOMAIN" "$CODER_DOMAIN" \
    "$ROOT_DIR/deploy/keycloak/realm-export.json" <<'PY'
import sys
import json
import urllib.request
import urllib.error

keycloak_url, admin_user, admin_pass = sys.argv[1:4]
realm, client_id = sys.argv[4:6]
pad_domain, auth_domain, coder_domain = sys.argv[6:9]
realm_export_path = sys.argv[9]


def api_req(method, path, data=None, token=None, headers=None):
    url = f"{keycloak_url}{path}"
    h = headers or {}
    if token:
        h['Authorization'] = f'Bearer {token}'
    if data and 'Content-Type' not in h:
        h['Content-Type'] = 'application/json'
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, method=method, data=body, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def get_token():
    data = {
        'grant_type': 'password',
        'client_id': 'admin-cli',
        'username': admin_user,
        'password': admin_pass,
    }
    status, body = api_req('POST', '/realms/master/protocol/openid-connect/token', data=data)
    if status != 200:
        print(f"ERROR: Keycloak admin login failed ({status}): {body}", file=sys.stderr)
        sys.exit(1)
    return json.loads(body)['access_token']


token = get_token()

# 1. Realm import on fresh DB.
status, _ = api_req('GET', f'/admin/realms/{realm}', token=token)
if status == 404:
    print(f"Realm '{realm}' not found; importing {realm_export_path}...")
    with open(realm_export_path) as f:
        realm_data = json.load(f)
    # Strip IDs so Keycloak regenerates them safely on import.
    realm_data.pop('id', None)
    status, body = api_req('POST', '/admin/realms', data=realm_data, token=token)
    if status not in (201, 204):
        print(f"ERROR: realm import failed ({status}): {body}", file=sys.stderr)
        sys.exit(1)
    print(f"Realm '{realm}' imported.")
elif status == 200:
    print(f"Realm '{realm}' already exists; reconciling settings...")
else:
    print(f"ERROR: could not check realm ({status})", file=sys.stderr)
    sys.exit(1)

# 2. Reconcile client redirect URIs and web origins.
status, body = api_req('GET', f'/admin/realms/{realm}/clients?clientId={client_id}', token=token)
if status != 200 or not json.loads(body):
    print(f"ERROR: client '{client_id}' not found in realm '{realm}'", file=sys.stderr)
    sys.exit(1)
client = json.loads(body)[0]
client_uuid = client['id']

redirect_uris = [
    f"https://{pad_domain}/api/auth/callback",
    f"https://{coder_domain}/api/v2/users/oidc/callback",
]
web_origins = [
    f"https://{pad_domain}",
    f"https://{coder_domain}",
]

client_update = {
    'redirectUris': redirect_uris,
    'webOrigins': web_origins,
    'standardFlowEnabled': True,
    'implicitFlowEnabled': False,
    'directAccessGrantsEnabled': False,
    'serviceAccountsEnabled': False,
    'publicClient': False,
}
status, body = api_req('PUT', f'/admin/realms/{realm}/clients/{client_uuid}', data=client_update, token=token)
if status not in (201, 204):
    print(f"ERROR: client update failed ({status}): {body}", file=sys.stderr)
    sys.exit(1)
print(f"Client '{client_id}' reconciled.")

# 3. Ensure realm roles.
for role_name in ('pad-user', 'admin'):
    status, _ = api_req('GET', f'/admin/realms/{realm}/roles/{role_name}', token=token)
    if status == 404:
        status, body = api_req('POST', f'/admin/realms/{realm}/roles', data={'name': role_name}, token=token)
        if status not in (201, 204):
            print(f"ERROR: role creation failed ({status}): {body}", file=sys.stderr)
            sys.exit(1)
        print(f"Role '{role_name}' created.")
    elif status == 200:
        print(f"Role '{role_name}' already exists.")
    else:
        print(f"ERROR: could not check role '{role_name}' ({status})", file=sys.stderr)
        sys.exit(1)

# 4. Reconcile session lifetimes (8h idle, 7d max).
# Values are in seconds.
realm_update = {
    'ssoSessionIdleTimeout': 28800,
    'ssoSessionMaxLifespan': 604800,
    'offlineSessionIdleTimeout': 2592000,
}
status, body = api_req('PUT', f'/admin/realms/{realm}', data=realm_update, token=token)
if status not in (201, 204):
    print(f"ERROR: realm update failed ({status}): {body}", file=sys.stderr)
    sys.exit(1)
print("Session lifetimes reconciled.")

print("Keycloak bootstrap complete.")
PY
