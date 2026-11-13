#!/bin/bash
set -e

# Validate the environment before starting. In development mode (PAD_DEV_MODE=true)
# the preflight is skipped so local host-networking stacks still work.
preflight() {
    if [[ "${PAD_DEV_MODE:-false}" =~ ^([Tt][Rr][Uu][Ee]|1)$ ]]; then
        return 0
    fi

    local required=(
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
    )

    local name value
    for name in "${required[@]}"; do
        value="${!name:-}"
        if [[ -z "$value" ]]; then
            echo "PREFLIGHT FAILED: required environment variable is empty: $name" >&2
            exit 1
        fi
        # Reject documented placeholder values without printing the value.
        case "$value" in
            __CHANGE_ME__|admin123|redis123|your_*)
                echo "PREFLIGHT FAILED: required environment variable is still set to a placeholder: $name" >&2
                exit 1
                ;;
        esac
    done

    # The Coder host is protected behind the gateway in production. A shared
    # cookie domain is required so Pad can gate Coder without leaking host-only
    # cookies that sibling hosts cannot receive. Accept both `.example.com` and
    # `example.com`; browsers treat them the same.
    local cookie_domain="${COOKIE_DOMAIN#.}"
    if [[ "$cookie_domain" != *.* ]]; then
        echo "PREFLIGHT FAILED: required environment variable must be a shared parent domain: COOKIE_DOMAIN" >&2
        exit 1
    fi
}

preflight

# Start the application behind the Caddy reverse proxy. Trust forwarded headers
# only from the configured proxy peers (Caddy by default).
exec uvicorn main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers "$API_WORKERS" \
    --proxy-headers \
    --forwarded-allow-ips "${TRUSTED_PROXY_IPS:-*}"
