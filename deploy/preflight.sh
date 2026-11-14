#!/usr/bin/env bash
set -euo pipefail

# Compose-wide preflight check.
# Usage: deploy/preflight.sh <env-file>
# Exits non-zero before any container would start if a required value is missing,
# still a placeholder, or violates a production guard.

if [[ $# -lt 1 ]]; then
    echo "Usage: ${0##*/} <env-file>" >&2
    exit 1
fi

ENV_FILE="$1"

if [[ ! -f "$ENV_FILE" ]]; then
    echo "PREFLIGHT FAILED: env file not found: $ENV_FILE" >&2
    exit 1
fi

# Load the env file without executing arbitrary code.
set -a
# shellcheck source=/dev/null
source "$ENV_FILE"
set +a

PROFILE="${PROFILE:-}"

fail() {
    echo "PREFLIGHT FAILED: $1" >&2
    exit 1
}

is_placeholder() {
    local value="$1"
    case "$value" in
        ""|__CHANGE_ME__|admin123|redis123|your_*|00000000-0000-0000-0000-000000000000)
            return 0
            ;;
    esac
    return 1
}

# ---------------------------------------------------------------------------
# Required variables across all services.
# ---------------------------------------------------------------------------
required=(
    POSTGRES_PASSWORD
    REDIS_PASSWORD
    KEYCLOAK_ADMIN_PASSWORD
    OIDC_CLIENT_SECRET
    CODER_API_KEY
    PAD_DOMAIN
    AUTH_DOMAIN
    CODER_DOMAIN
    COOKIE_DOMAIN
    OIDC_SERVER_URL
    REDIRECT_URI
    FRONTEND_URL
    ADMIN_ALLOWLIST
    ACME_EMAIL
    PAD_ALLOWED_ROLES
    CADDYFILE
    POSTGRES_USER
    POSTGRES_DB
    KEYCLOAK_ADMIN
    KEYCLOAK_DB
    CODER_DB
    CODER_DB_PASSWORD_URLENCODED
    CODER_TEMPLATE_ID
    CODER_DEFAULT_ORGANIZATION
    DOCKER_GROUP_ID
    CADDY_IMAGE
    POSTGRES_IMAGE
    REDIS_IMAGE
    KEYCLOAK_IMAGE
    CODER_IMAGE
    PAD_IMAGE
)

for name in "${required[@]}"; do
    value="${!name:-}"
    if is_placeholder "$value"; then
        fail "required variable is empty or still set to a placeholder: $name"
    fi
done

# ---------------------------------------------------------------------------
# Cookie domain must be a shared parent of the three hosts.
# ---------------------------------------------------------------------------
cookie_domain="${COOKIE_DOMAIN#.}"
if [[ "$cookie_domain" != *.* ]]; then
    fail "COOKIE_DOMAIN must be a shared parent domain (e.g. .example.com)"
fi

# ---------------------------------------------------------------------------
# Production guard: ADMIN_ALLOWLIST must not be open or malformed.
# ---------------------------------------------------------------------------
if [[ "$PROFILE" == "production" ]]; then
    if [[ "$ADMIN_ALLOWLIST" == "0.0.0.0/0 ::/0" ]] || \
       [[ "$ADMIN_ALLOWLIST" == *"0.0.0.0/0"* ]] || \
       [[ "$ADMIN_ALLOWLIST" == *"::/0"* ]]; then
        fail "ADMIN_ALLOWLIST is open (0.0.0.0/0 ::/0) in production"
    fi

    # Basic CIDR sanity: every token should look like an IPv4/IPv6 CIDR or IP.
    read -ra allowlist <<< "$ADMIN_ALLOWLIST"
    for cidr in "${allowlist[@]}"; do
        if [[ -z "$cidr" ]]; then
            continue
        fi
        # Accept IPv4 CIDR, IPv4 address, IPv6 CIDR or IPv6 address.
        if [[ ! "$cidr" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}(/[0-9]+)?$ ]] && \
           [[ ! "$cidr" =~ ^([0-9a-fA-F:]+)(/[0-9]+)?$ ]]; then
            fail "ADMIN_ALLOWLIST contains a malformed CIDR: $cidr"
        fi
    done
fi

echo "Preflight OK (profile=$PROFILE)" >&2
