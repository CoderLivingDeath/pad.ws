#!/usr/bin/env bash
set -euo pipefail

# One-command deployment for the Pad auth gateway.
#
# Usage:
#   scripts/deploy.sh up [--profile local|staging|production] [--set KEY=VALUE] ...
#   scripts/deploy.sh down
#   scripts/deploy.sh destroy --yes-i-want-to-destroy-data
#   scripts/deploy.sh status
#   scripts/deploy.sh logs [-f]
#   scripts/deploy.sh backup
#   scripts/deploy.sh restore [--drill]
#   scripts/deploy.sh rotate-key
#   scripts/deploy.sh upgrade <version>
#   scripts/deploy.sh rollback

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="$ROOT_DIR/docker-compose.prod.yml"
COMPOSE_TEST_FILE="$ROOT_DIR/compose.test.yml"
PREFLIGHT_SCRIPT="$ROOT_DIR/deploy/preflight.sh"
RELEASES_DIR="${RELEASES_DIR:-$ROOT_DIR/deploy/releases}"
STATE_DIR="${STATE_DIR:-$ROOT_DIR/.deploy-state}"

cd "$ROOT_DIR"

# ---------------------------------------------------------------------------
# Defaults and configuration resolution.
# ---------------------------------------------------------------------------
PROFILE="${PROFILE:-local}"
PROFILE_SOURCE="${PROFILE_SOURCE:-default}"
ENV_FILE="${ENV_FILE:-$ROOT_DIR/.env}"
RESOLVED_ENV=""
CLI_OVERRIDES=()
DRY_RUN="${DRY_RUN:-false}"

# Record variables that are set in the process environment so they are not
# overwritten by profile or .env files (precedence: env > profile > .env).
declare -A ENV_VARS
for key in $(compgen -e); do
    ENV_VARS["$key"]=1
done

usage() {
    local code="${1:-1}"
    cat <<'EOF'
Usage: scripts/deploy.sh <command> [options]

Commands:
  up              Resolve config, generate secrets, start the stack and run smoke checks.
  down            Stop the stack.
  destroy         Stop the stack and delete all volumes (requires --yes-i-want-to-destroy-data).
  status          Show service health, image digests, certificate, backup and key age.
  logs [-f]       Show service logs (pass -f to follow).
  backup          Back up all PostgreSQL databases.
  restore         Restore databases from the latest dumps (pass --drill for an isolated drill).
  rotate-key      Rotate the Coder API key and restart Pad.
  upgrade <ver>   Back up, pin target digests and deploy a release version.
  rollback        Restore the previous release manifest and database backup.

Up options:
  --profile <name>          Select deploy profile (local, staging, production).
  --set KEY=VALUE           Override any configuration value.
  --domain <domain>         Shorthand for --set PAD_DOMAIN=<domain> etc.
  --allowlist <cidrs>       Shorthand for --set ADMIN_ALLOWLIST=<cidrs>.
  --dry-run                 Resolve and validate config without starting containers.

Examples:
  scripts/deploy.sh up --profile local
  scripts/deploy.sh up --profile production --domain example.com --allowlist "203.0.113.0/24"
  make deploy PROFILE=production DOMAIN=example.com
EOF
    exit "$code"
}

# ---------------------------------------------------------------------------
# Helper functions.
# ---------------------------------------------------------------------------
compose_cmd() {
    if [[ "$PROFILE" == "local" || "$PROFILE" == "staging" ]]; then
        echo "docker compose -f $COMPOSE_FILE -f $COMPOSE_TEST_FILE --env-file $ENV_FILE"
    else
        echo "docker compose -f $COMPOSE_FILE --env-file $ENV_FILE"
    fi
}

compose() {
    $(compose_cmd) "$@"
}

require_env() {
    if [[ ! -f "$ENV_FILE" ]]; then
        echo "ERROR: .env file missing; run 'up' first" >&2
        exit 1
    fi
}

# Load an env file into the current shell, ignoring unsafe lines and keys that
# were already set in the process environment.
load_env_file() {
    local file="$1"
    if [[ ! -f "$file" ]]; then
        return 0
    fi
    while IFS= read -r line || [[ -n "$line" ]]; do
        [[ -z "$line" ]] && continue
        [[ "$line" =~ ^[[:space:]]*# ]] && continue
        if [[ "$line" =~ ^([A-Za-z_][A-Za-z0-9_]*)=(.*)$ ]]; then
            local key="${BASH_REMATCH[1]}"
            if [[ -n "${ENV_VARS[$key]:-}" ]]; then
                continue
            fi
            printf -v "$key" '%s' "${BASH_REMATCH[2]}"
        fi
    done < "$file"
}

# Generate a secure secret if not already present.
ensure_secret() {
    local key="$1"
    local length="${2:-32}"
    local current
    current="${!key:-}"
    if [[ -z "$current" ]] || [[ "$current" == "__CHANGE_ME__" ]]; then
        printf -v "$key" '%s' "$(openssl rand -hex "$length")"
    fi
}

# ---------------------------------------------------------------------------
# Configuration resolution.
# ---------------------------------------------------------------------------
resolve_config() {
    local profile_file="$ROOT_DIR/deploy/profiles/${PROFILE}.env"
    if [[ ! -f "$profile_file" ]]; then
        echo "ERROR: unknown profile: $PROFILE" >&2
        exit 1
    fi

    mkdir -p "$STATE_DIR"
    RESOLVED_ENV="$(mktemp -t deploy-resolved-XXXXXX.env)"

    # Layer 5: release manifest defaults (image digests).
    local release_manifest
    release_manifest="$RELEASES_DIR/0.1.0.json"
    if [[ -f "$release_manifest" ]]; then
        python3 - "$release_manifest" <<'PY' > "$STATE_DIR/release.env"
import sys, json
with open(sys.argv[1]) as f:
    data = json.load(f)
for k, v in data.get('images', {}).items():
    print(f"{k}={v}")
PY
        load_env_file "$STATE_DIR/release.env"
    fi

    # Layer 4: .env (if it exists and is not a placeholder-only template).
    if [[ -f "$ENV_FILE" ]]; then
        load_env_file "$ENV_FILE"
    fi

    # Layer 3: profile file.
    load_env_file "$profile_file"

    # Layer 2: process environment.
    # Already present via shell environment; no action needed.

    # Layer 1: CLI overrides.
    for override in "${CLI_OVERRIDES[@]}"; do
        local key value
        key="${override%%=*}"
        value="${override#*=}"
        printf -v "$key" '%s' "$value"
    done

    # Generate missing secrets (local profile defaults).
    ensure_secret POSTGRES_PASSWORD 16
    ensure_secret REDIS_PASSWORD 16
    ensure_secret KEYCLOAK_ADMIN_PASSWORD 16
    ensure_secret OIDC_CLIENT_SECRET 32
    ensure_secret CODER_API_KEY 32
    if [[ -z "${CODER_DB_PASSWORD_URLENCODED:-}" ]] || [[ "$CODER_DB_PASSWORD_URLENCODED" == "__CHANGE_ME__" ]]; then
        CODER_DB_PASSWORD_URLENCODED="$POSTGRES_PASSWORD"
    fi
    if [[ -z "${DOCKER_GROUP_ID:-}" ]] || [[ "$DOCKER_GROUP_ID" == "__CHANGE_ME__" ]]; then
        DOCKER_GROUP_ID="$(getent group docker 2>/dev/null | cut -d: -f3 || echo "999")"
    fi

    # Local profile: derive URLs from domains if not already set.
    if [[ "$PROFILE" == "local" ]]; then
        : "${OIDC_SERVER_URL:=https://${AUTH_DOMAIN}}"
        : "${REDIRECT_URI:=https://${PAD_DOMAIN}/api/auth/callback}"
        : "${FRONTEND_URL:=https://${PAD_DOMAIN}}"
        : "${CODER_URL:=https://${CODER_DOMAIN}}"
    fi

    # Pad local image: use the test build tag.
    if [[ "$PROFILE" == "local" ]]; then
        PAD_IMAGE="pad-ws:test"
    fi

    # Write resolved config, preserving key order and without secrets in comments.
    {
        echo "# Resolved configuration generated by scripts/deploy.sh"
        echo "# Profile: $PROFILE"
        echo "PROFILE=$PROFILE"
        for key in PROFILE PAD_DOMAIN AUTH_DOMAIN CODER_DOMAIN COOKIE_DOMAIN ACME_EMAIL CADDYFILE \
                   OIDC_SERVER_URL REDIRECT_URI FRONTEND_URL OIDC_INTERNAL_URL CODER_URL CODER_INTERNAL_URL \
                   OIDC_REALM OIDC_CLIENT_ID OIDC_CLIENT_SECRET \
                   POSTGRES_USER POSTGRES_PASSWORD POSTGRES_DB POSTGRES_HOST POSTGRES_PORT \
                   REDIS_PASSWORD REDIS_HOST REDIS_PORT \
                   KEYCLOAK_ADMIN KEYCLOAK_ADMIN_PASSWORD KEYCLOAK_DB \
                   CODER_API_KEY CODER_API_KEY_CREATED_AT CODER_TEMPLATE_ID CODER_DEFAULT_ORGANIZATION \
                   CODER_WORKSPACE_NAME CODER_DB CODER_DB_PASSWORD_URLENCODED DOCKER_GROUP_ID \
                   ADMIN_ALLOWLIST TRUSTED_PROXY_IPS PAD_ALLOWED_ROLES API_WORKERS SESSION_COOKIE_NAME \
                   STATIC_DIR ASSETS_DIR BACKUP_RETENTION_DAYS \
                   CADDY_IMAGE POSTGRES_IMAGE REDIS_IMAGE KEYCLOAK_IMAGE CODER_IMAGE PAD_IMAGE; do
            value="${!key:-}"
            if [[ -n "$value" ]]; then
                # Quote values with spaces so both shell parsers and
                # ``docker compose --env-file`` read them as one value.
                if [[ "$value" == *" "* ]]; then
                    echo "${key}=\"${value}\""
                else
                    echo "${key}=${value}"
                fi
            else
                echo "# ${key}="
            fi
        done
    } > "$RESOLVED_ENV"
    chmod 600 "$RESOLVED_ENV"

    # Run compose-wide preflight before docker compose validation so placeholders
    # are reported by name instead of as compose errors.
    if [[ -x "$PREFLIGHT_SCRIPT" ]]; then
        "$PREFLIGHT_SCRIPT" "$RESOLVED_ENV"
    fi

    # Persist the resolved config as .env for docker compose and other scripts,
    # merging with the existing file so operator-supplied unknown keys survive.
    if [[ -f "$ENV_FILE" ]]; then
        merge_env_file "$ENV_FILE" "$RESOLVED_ENV"
    else
        cp "$RESOLVED_ENV" "$ENV_FILE"
    fi
    chmod 600 "$ENV_FILE"

    # Validate with docker compose config.
    if ! $(compose_cmd) config >/dev/null 2>&1; then
        echo "ERROR: docker compose config validation failed" >&2
        $(compose_cmd) config >&2 || true
        exit 1
    fi
}

# ---------------------------------------------------------------------------
# Health and smoke gating.
# ---------------------------------------------------------------------------
wait_for_healthy() {
    local timeout=300
    local interval=5
    local elapsed=0
    echo "Waiting for services to become healthy (timeout ${timeout}s)..."
    while [[ "$elapsed" -lt "$timeout" ]]; do
        local pending=()
        for service in caddy pad postgres redis keycloak coder; do
            local container status
            container="$(compose ps -q "$service" 2>/dev/null || true)"
            if [[ -z "$container" ]]; then
                pending+=("$service:missing")
                continue
            fi
            status="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container" 2>/dev/null || true)"
            if [[ "$status" != "healthy" && "$status" != "running" ]]; then
                pending+=("$service:$status")
            fi
        done
        if [[ ${#pending[@]} -eq 0 ]]; then
            echo "All services are healthy."
            return 0
        fi
        echo "  pending: ${pending[*]}"
        sleep "$interval"
        elapsed=$((elapsed + interval))
    done
    echo "ERROR: services did not become healthy within ${timeout}s" >&2
    compose logs --tail=80 >&2 || true
    return 1
}

run_smoke() {
    echo "Running post-deploy smoke checks..."
    local pad_url="https://${PAD_DOMAIN}"
    local auth_url="https://${AUTH_DOMAIN}"
    local coder_url="https://${CODER_DOMAIN}"
    local ca_bundle=""
    if [[ "$PROFILE" == "local" ]]; then
        ca_bundle="$ROOT_DIR/caddy-root.crt"
    fi

    local smoke_env=(
        "PAD_BASE_URL=$pad_url"
        "AUTH_BASE_URL=$auth_url"
        "CODER_BASE_URL=$coder_url"
    )
    if [[ -n "$ca_bundle" && -f "$ca_bundle" ]]; then
        smoke_env+=("CA_BUNDLE=$ca_bundle")
    fi
    if ! env "${smoke_env[@]}" bash "$ROOT_DIR/scripts/smoke-test.sh"; then
        echo "ERROR: smoke check failed" >&2
        compose logs --tail=80 >&2 || true
        return 1
    fi
    echo "Smoke checks passed."
}

# ---------------------------------------------------------------------------
# Release manifest helpers.
# ---------------------------------------------------------------------------
record_release() {
    local version="${1:-current}"
    local manifest="$RELEASES_DIR/${version}.json"
    if [[ ! -f "$manifest" ]]; then
        echo "ERROR: release manifest not found: $manifest" >&2
        return 1
    fi
    cp "$manifest" "$STATE_DIR/current.json"
}

save_previous_release() {
    if [[ -f "$STATE_DIR/current.json" ]]; then
        cp "$STATE_DIR/current.json" "$STATE_DIR/previous.json"
    fi
}

load_release_images() {
    local manifest="$1"
    if [[ ! -f "$manifest" ]]; then
        return 1
    fi
    python3 - "$manifest" <<'PY' > "$STATE_DIR/release.env"
import sys, json
with open(sys.argv[1]) as f:
    data = json.load(f)
for k, v in data.get('images', {}).items():
    print(f"{k}={v}")
PY
    # During upgrade/rollback the manifest explicitly chosen by the operator
    # must win, so force-set the image variables regardless of env precedence.
    while IFS= read -r line; do
        [[ -z "$line" ]] && continue
        local key="${line%%=*}" value="${line#*=}"
        printf -v "$key" '%s' "$value"
    done < "$STATE_DIR/release.env"
}

# Merge source env file into target env file. Existing keys are updated,
# missing keys are appended, and unknown keys/comments are preserved.
merge_env_file() {
    local target="$1"
    local source="$2"
    python3 - "$target" "$source" <<'PY'
import sys
target = sys.argv[1]
source = sys.argv[2]

updates = {}
with open(source) as f:
    for line in f:
        line = line.rstrip('\n')
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        updates[key] = value

with open(target) as f:
    lines = f.readlines()

seen = set()
with open(target, 'w') as f:
    for line in lines:
        original = line.rstrip('\n')
        if not original or original.startswith('#') or '=' not in original:
            f.write(original + '\n')
            continue
        key = original.split('=', 1)[0]
        if key in updates:
            f.write(f"{key}={updates[key]}\n")
            seen.add(key)
        else:
            f.write(original + '\n')
    for key, value in updates.items():
        if key not in seen:
            f.write(f"{key}={value}\n")
PY
    chmod 600 "$target"
}

# Update specific KEY=VALUE pairs in an env file, preserving other lines.
update_env_values() {
    local env_file="$1"
    shift
    python3 - "$env_file" "$@" <<'PY'
import sys
env_file = sys.argv[1]
updates = {}
for arg in sys.argv[2:]:
    if '=' in arg:
        key, value = arg.split('=', 1)
        updates[key] = value

with open(env_file) as f:
    lines = f.readlines()

seen = set()
with open(env_file, 'w') as f:
    for line in lines:
        original = line.rstrip('\n')
        if not original or original.startswith('#') or '=' not in original:
            f.write(original + '\n')
            continue
        key = original.split('=', 1)[0]
        if key in updates:
            f.write(f"{key}={updates[key]}\n")
            seen.add(key)
        else:
            f.write(original + '\n')
    for key, value in updates.items():
        if key not in seen:
            f.write(f"{key}={value}\n")
PY
    chmod 600 "$env_file"
}

# Apply image digests from a release manifest to $ENV_FILE and verify that
# docker compose config resolves them.
apply_release_images() {
    local manifest="$1"
    load_release_images "$manifest"

    local image_vars=()
    for var in CADDY_IMAGE POSTGRES_IMAGE REDIS_IMAGE KEYCLOAK_IMAGE CODER_IMAGE; do
        image_vars+=("${var}=${!var}")
    done
    update_env_values "$ENV_FILE" "${image_vars[@]}"

    echo "Verifying image digests against manifest..."
    if ! assert_release_images "$manifest"; then
        echo "ERROR: image digest verification failed" >&2
        exit 1
    fi
}

# Assert that the resolved compose images match the manifest digests.
assert_release_images() {
    local manifest="$1"
    python3 - "$manifest" "$(compose_cmd) config" <<'PY'
import sys, json, subprocess, yaml
manifest_path = sys.argv[1]
compose_cmd = sys.argv[2]

with open(manifest_path) as f:
    manifest = json.load(f)
expected = manifest.get('images', {})

config = subprocess.check_output(compose_cmd, shell=True, text=True)
data = yaml.safe_load(config)
services = data.get('services', {})

failures = []
for var, image in expected.items():
    service = var.replace('_IMAGE', '').lower()
    actual = services.get(service, {}).get('image', '')
    if actual != image:
        failures.append(f"{service}: expected {image}, got {actual}")

if failures:
    print("Image digest mismatch:", file=sys.stderr)
    for f in failures:
        print(f"  - {f}", file=sys.stderr)
    sys.exit(1)
print("Image digests verified against manifest.")
PY
}

# Record the most recent backup dumps in state.
record_last_backup() {
    local backup_dir="${BACKUP_DIR:-$ROOT_DIR/backups}"
    python3 - "$backup_dir" "$STATE_DIR/last-backup.json" <<'PY'
import sys, os, json, glob
backup_dir = sys.argv[1]
out = sys.argv[2]

dumps = {}
for db in ('pad', 'keycloak', 'coder'):
    files = glob.glob(os.path.join(backup_dir, f"{db}_*.dump.gz"))
    if files:
        latest = max(files, key=os.path.getmtime)
        dumps[db] = os.path.basename(latest)

with open(out, 'w') as f:
    json.dump({'directory': backup_dir, 'dumps': dumps}, f, indent=2)
PY

    # If a previous-release state exists, attach this backup to it.
    if [[ -f "$STATE_DIR/previous.json" ]]; then
        python3 - "$STATE_DIR/previous.json" "$STATE_DIR/last-backup.json" "$STATE_DIR/previous.json" <<'PY'
import sys, json
prev_path = sys.argv[1]
backup_path = sys.argv[2]
out_path = sys.argv[3]

with open(prev_path) as f:
    state = json.load(f)
with open(backup_path) as f:
    state['backup'] = json.load(f)

with open(out_path, 'w') as f:
    json.dump(state, f, indent=2)
PY
    fi
}

# Print the three database dump paths recorded for rollback.
get_previous_backup_paths() {
    python3 - "$STATE_DIR/previous.json" <<'PY'
import sys, json, os
with open(sys.argv[1]) as f:
    d = json.load(f)
backup = d.get('backup', {})
directory = backup.get('directory', '')
for db in ('pad', 'keycloak', 'coder'):
    print(os.path.join(directory, backup.get('dumps', {}).get(db, '')))
PY
}

# ---------------------------------------------------------------------------
# Subcommand implementations.
# ---------------------------------------------------------------------------
cmd_up() {
    resolve_config

    if [[ "$DRY_RUN" == "true" ]]; then
        echo "Dry run: configuration resolved and validated."
        echo "Profile: $PROFILE"
        echo "Domains: PAD_DOMAIN=$PAD_DOMAIN, AUTH_DOMAIN=$AUTH_DOMAIN, CODER_DOMAIN=$CODER_DOMAIN"
        echo "Allowlist: $ADMIN_ALLOWLIST"
        echo "Caddy image: $CADDY_IMAGE"
        echo "Pad image: $PAD_IMAGE"
        echo "Resolved env: $RESOLVED_ENV"
        return 0
    fi

    # Local profile: build Pad from the working tree.
    if [[ "$PROFILE" == "local" ]]; then
        echo "Building Pad image from working tree..."
        compose build pad
    fi

    echo "Starting infrastructure services..."
    if [[ "$PROFILE" == "local" || "$PROFILE" == "staging" ]]; then
        compose up -d postgres redis keycloak pad caddy
    else
        compose up -d postgres redis keycloak pad caddy
    fi

    # Export Caddy internal CA for local profile.
    if [[ "$PROFILE" == "local" ]]; then
        echo "Exporting Caddy internal CA..."
        for _ in $(seq 1 30); do
            if compose cp caddy:/data/caddy/pki/authorities/local/root.crt "$ROOT_DIR/caddy-root.crt" 2>/dev/null; then
                chmod 644 "$ROOT_DIR/caddy-root.crt"
                break
            fi
            sleep 2
        done
    fi

    # Start Coder after Caddy is healthy.
    echo "Starting Coder..."
    compose up -d coder

    wait_for_healthy

    # Bootstrap Keycloak.
    echo "Bootstrapping Keycloak..."
    ENV_FILE="$ENV_FILE" bash "$ROOT_DIR/scripts/bootstrap-keycloak.sh"

    # Bootstrap Coder.
    echo "Bootstrapping Coder..."
    ENV_FILE="$ENV_FILE" bash "$ROOT_DIR/scripts/bootstrap-coder.sh"

    # The template and organization are discovered during bootstrap, so validate
    # them afterwards and restart Pad to pick up the values written to .env.
    local post_bootstrap_failed=0
    for key in CODER_TEMPLATE_ID CODER_DEFAULT_ORGANIZATION; do
        local value
        value="$(grep -E "^${key}=" "$ENV_FILE" | tail -1 | cut -d= -f2- || true)"
        if [[ -z "$value" ]] || [[ "$value" == "__CHANGE_ME__" ]] || [[ "$value" == "00000000-0000-0000-0000-000000000000" ]]; then
            echo "ERROR: ${key} was not discovered during Coder bootstrap; create the docker template in the Coder UI and rerun." >&2
            post_bootstrap_failed=1
        fi
    done
    if [[ "$post_bootstrap_failed" -ne 0 ]]; then
        return 1
    fi
    echo "Restarting Pad with the discovered Coder identifiers..."
    compose up -d --force-recreate pad
    wait_for_healthy

    # Run smoke checks.
    run_smoke

    # Record current release manifest.
    record_release "0.1.0"

    echo
    echo "=== Deployment complete ==="
    echo "Profile: $PROFILE"
    echo "Pad:    https://${PAD_DOMAIN}"
    echo "Auth:   https://${AUTH_DOMAIN}"
    echo "Coder:  https://${CODER_DOMAIN}"
}

cmd_down() {
    require_env
    compose down "$@"
}

cmd_destroy() {
    if [[ "${1:-}" != "--yes-i-want-to-destroy-data" ]]; then
        echo "ERROR: destroy requires --yes-i-want-to-destroy-data" >&2
        echo "This will delete all containers, volumes and local data." >&2
        exit 1
    fi
    require_env
    compose down -v
    rm -rf "$STATE_DIR"
    echo "Stack destroyed and volumes removed."
}

cmd_status() {
    require_env
    ENV_FILE="$ENV_FILE" bash "$ROOT_DIR/scripts/status.sh"
}

cmd_logs() {
    require_env
    compose logs "$@"
}

cmd_backup() {
    require_env
    ENV_FILE="$ENV_FILE" COMPOSE_FILE="$COMPOSE_FILE" bash "$ROOT_DIR/scripts/backup-postgres.sh"
    record_last_backup
}

cmd_restore() {
    require_env
    ENV_FILE="$ENV_FILE" COMPOSE_FILE="$COMPOSE_FILE" bash "$ROOT_DIR/scripts/restore-postgres.sh" "$@"
}

cmd_rotate_key() {
    require_env
    ENV_FILE="$ENV_FILE" COMPOSE_FILE="$COMPOSE_FILE" bash "$ROOT_DIR/scripts/rotate-coder-key.sh"
}

cmd_upgrade() {
    local version="${1:-}"
    if [[ -z "$version" ]]; then
        echo "ERROR: upgrade requires a version argument" >&2
        exit 1
    fi
    resolve_config
    save_previous_release

    echo "Creating pre-upgrade backup..."
    cmd_backup

    echo "Applying release $version image digests..."
    local manifest="$RELEASES_DIR/${version}.json"
    if [[ ! -f "$manifest" ]]; then
        echo "ERROR: release manifest not found: $manifest" >&2
        exit 1
    fi
    apply_release_images "$manifest"
    record_release "$version"

    echo "Recreating services with new images..."
    compose up -d --force-recreate

    wait_for_healthy
    run_smoke

    echo "Upgrade to $version complete."
}

cmd_rollback() {
    if [[ ! -f "$STATE_DIR/previous.json" ]]; then
        echo "ERROR: no previous release recorded" >&2
        exit 1
    fi
    resolve_config

    echo "Restoring previous release image digests..."
    apply_release_images "$STATE_DIR/previous.json"

    echo "Restoring database backup from previous release..."
    local backup_paths=()
    while IFS= read -r path; do
        backup_paths+=("$path")
    done < <(get_previous_backup_paths)
    if [[ ${#backup_paths[@]} -ne 3 ]]; then
        echo "ERROR: could not determine previous backup paths" >&2
        exit 1
    fi
    cmd_restore "${backup_paths[@]}"

    echo "Recreating services with previous images..."
    compose up -d --force-recreate

    wait_for_healthy
    run_smoke

    echo "Rollback complete."
}

# ---------------------------------------------------------------------------
# Main entry point (skip when sourced by tests).
# ---------------------------------------------------------------------------
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    if [[ $# -lt 1 ]]; then
        usage
    fi

    COMMAND="$1"
    shift

    # Global options can appear before or after command; parse only the ones we know.
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --profile)
                PROFILE="$2"
                PROFILE_SOURCE=cli
                shift 2
                ;;
            --profile=*)
                PROFILE="${1#*=}"
                PROFILE_SOURCE=cli
                shift
                ;;
            --set)
                CLI_OVERRIDES+=("$2")
                shift 2
                ;;
            --set=*)
                CLI_OVERRIDES+=("${1#*=}")
                shift
                ;;
            --domain)
                local_domain="$2"
                CLI_OVERRIDES+=("PAD_DOMAIN=pad.${local_domain}")
                CLI_OVERRIDES+=("AUTH_DOMAIN=auth.${local_domain}")
                CLI_OVERRIDES+=("CODER_DOMAIN=coder.${local_domain}")
                CLI_OVERRIDES+=("COOKIE_DOMAIN=.${local_domain}")
                CLI_OVERRIDES+=("OIDC_SERVER_URL=https://auth.${local_domain}")
                CLI_OVERRIDES+=("REDIRECT_URI=https://pad.${local_domain}/api/auth/callback")
                CLI_OVERRIDES+=("FRONTEND_URL=https://pad.${local_domain}")
                CLI_OVERRIDES+=("CODER_URL=https://coder.${local_domain}")
                shift 2
                ;;
            --allowlist)
                CLI_OVERRIDES+=("ADMIN_ALLOWLIST=$2")
                shift 2
                ;;
            --dry-run)
                DRY_RUN=true
                shift
                ;;
            -h|--help)
                usage 0
                ;;
            *)
                break
                ;;
        esac
    done

    # Use a stable state directory.
    mkdir -p "$STATE_DIR"

    # If no profile was passed on the CLI, use the one recorded in .env so that
    # subcommands like status/logs/backup work without re-specifying it.
    if [[ "$PROFILE_SOURCE" != "cli" ]] && [[ -f "$ENV_FILE" ]]; then
        saved_profile="$(grep -E '^PROFILE=' "$ENV_FILE" | cut -d= -f2- || true)"
        if [[ -n "$saved_profile" ]]; then
            PROFILE="$saved_profile"
        fi
    fi

    case "$COMMAND" in
        up)
            cmd_up
            ;;
        down)
            cmd_down "$@"
            ;;
        destroy)
            cmd_destroy "$@"
            ;;
        status)
            cmd_status
            ;;
        logs)
            cmd_logs "$@"
            ;;
        backup)
            cmd_backup
            ;;
        restore)
            cmd_restore "$@"
            ;;
        rotate-key)
            cmd_rotate_key
            ;;
        upgrade)
            cmd_upgrade "$@"
            ;;
        rollback)
            cmd_rollback
            ;;
        -h|--help|help)
            usage 0
            ;;
        *)
            echo "Unknown command: $COMMAND" >&2
            usage
            ;;
    esac
fi
