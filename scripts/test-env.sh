#!/usr/bin/env bash
set -euo pipefail

# Local acceptance environment bootstrap for *.pad.test.
# Usage: test-env.sh up|down|status|logs

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT_DIR}/.env.test"
REAL_ENV_FILE="${ROOT_DIR}/.env"
COMPOSE="docker compose -f ${ROOT_DIR}/docker-compose.prod.yml -f ${ROOT_DIR}/compose.test.yml --env-file ${ENV_FILE}"

usage() {
    cat <<'EOF'
Usage: test-env.sh <command>

Commands:
  up      Build Pad from the working tree and start the *.pad.test stack.
  down    Stop and remove the test stack.
  status  Show running containers and their health.
  logs    Follow logs from all services.
EOF
    exit 1
}

# Generate .env.test from .env.local.template with test-only secrets.
# Realm import only happens on a fresh Keycloak database; if you change
# deploy/keycloak/realm-export.json, remove the Keycloak database volume
# (docker compose rm -s -v keycloak; docker volume rm keycloak_data is not
# needed because Keycloak stores data in postgres_data) and start again.
generate_env() {
    if [[ -f "${ENV_FILE}" ]]; then
        echo "Using existing ${ENV_FILE}" >&2
        return 0
    fi

    echo "Generating ${ENV_FILE} from .env.local.template with test-only secrets..." >&2

    if ! command -v openssl >/dev/null 2>&1; then
        echo "ERROR: openssl is required to generate test secrets" >&2
        exit 1
    fi

    local postgres_password redis_password keycloak_admin_password
    local coder_api_key coder_db_password docker_group_id

    postgres_password="$(openssl rand -hex 16)"
    redis_password="$(openssl rand -hex 16)"
    keycloak_admin_password="$(openssl rand -hex 16)"
    coder_api_key="$(openssl rand -hex 32)"
    coder_db_password="$(openssl rand -hex 16)"
    docker_group_id="$(getent group docker 2>/dev/null | cut -d: -f3 || echo "999")"

    # Placeholder IDs for Coder; replace them after following
    # tests/e2e/fixtures/coder.md and running scripts/bootstrap-coder.sh.
    local coder_org coder_template
    coder_org="00000000-0000-0000-0000-000000000000"
    coder_template="00000000-0000-0000-0000-000000000000"

    sed \
        -e "s/^POSTGRES_PASSWORD=__CHANGE_ME__$/POSTGRES_PASSWORD=${postgres_password}/" \
        -e "s/^REDIS_PASSWORD=__CHANGE_ME__$/REDIS_PASSWORD=${redis_password}/" \
        -e "s/^KEYCLOAK_ADMIN_PASSWORD=__CHANGE_ME__$/KEYCLOAK_ADMIN_PASSWORD=${keycloak_admin_password}/" \
        -e "s/^CODER_API_KEY=__CHANGE_ME__$/CODER_API_KEY=${coder_api_key}/" \
        -e "s/^CODER_DB_PASSWORD_URLENCODED=__CHANGE_ME__$/CODER_DB_PASSWORD_URLENCODED=${coder_db_password}/" \
        -e "s/^DOCKER_GROUP_ID=__CHANGE_ME__$/DOCKER_GROUP_ID=${docker_group_id}/" \
        -e "s/^CODER_DEFAULT_ORGANIZATION=__CHANGE_ME__$/CODER_DEFAULT_ORGANIZATION=${coder_org}/" \
        -e "s/^CODER_TEMPLATE_ID=__CHANGE_ME__$/CODER_TEMPLATE_ID=${coder_template}/" \
        "${ROOT_DIR}/.env.local.template" > "${ENV_FILE}"

    chmod 600 "${ENV_FILE}"
    echo "Wrote ${ENV_FILE}" >&2
}

# Copy .env.test to .env only when .env does not exist, so a real .env is never
# overwritten.
link_env() {
    if [[ -f "${REAL_ENV_FILE}" ]]; then
        echo "Keeping existing ${REAL_ENV_FILE} (refusing to overwrite a real .env)" >&2
        return 0
    fi

    cp "${ENV_FILE}" "${REAL_ENV_FILE}"
    chmod 600 "${REAL_ENV_FILE}"
    echo "Created ${REAL_ENV_FILE} from ${ENV_FILE}" >&2
}

cmd_up() {
    generate_env
    link_env

    echo "Starting test stack..." >&2
    ${COMPOSE} up -d --build

    echo "Waiting for services to become healthy (timeout 5 minutes)..." >&2
    local i
    for i in $(seq 1 60); do
        local pending
        pending="$(${COMPOSE} ps | grep -E '(starting| unhealthy)' || true)"
        if [[ -z "${pending}" ]]; then
            echo "All services are healthy." >&2
            break
        fi
        sleep 5
    done

    ${COMPOSE} ps

    cat <<'EOF'

=== Local acceptance environment ===
Pad:    https://pad.pad.test
Auth:   https://auth.pad.test
Coder:  https://coder.pad.test

Add the following entries to /etc/hosts if you have not already:
  127.0.0.1 pad.pad.test auth.pad.test coder.pad.test

To trust the Caddy internal CA:
  docker compose -f docker-compose.prod.yml -f compose.test.yml \
    --env-file .env.test cp caddy:/data/caddy/pki/authorities/local/root.crt ./caddy-root.crt
Then install ./caddy-root.crt into your browser or system trust store.

NOTE: The Keycloak realm export is imported only when the Keycloak database is
fresh. If you change deploy/keycloak/realm-export.json, remove the PostgreSQL
volume and start again:
  docker compose -f docker-compose.prod.yml -f compose.test.yml --env-file .env.test down -v
  scripts/test-env.sh up
EOF
}

cmd_down() {
    echo "Stopping test stack..." >&2
    ${COMPOSE} down "$@"
}

cmd_status() {
    ${COMPOSE} ps
}

cmd_logs() {
    ${COMPOSE} logs -f
}

main() {
    cd "${ROOT_DIR}"

    if [[ $# -lt 1 ]]; then
        usage
    fi

    local command="${1}"
    shift

    case "${command}" in
        up)
            cmd_up
            ;;
        down)
            cmd_down "$@"
            ;;
        status)
            cmd_status
            ;;
        logs)
            cmd_logs
            ;;
        -h|--help|help)
            usage
            ;;
        *)
            echo "Unknown command: ${command}" >&2
            usage
            ;;
    esac
}

main "$@"
