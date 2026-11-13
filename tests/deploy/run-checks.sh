#!/usr/bin/env bash
# Deployment and topology invariant checks.
#
# Validates the production compose file and supporting scripts.  Can be run
# without a running stack; checks that need the stack are skipped with a clear
# message.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
COMPOSE_FILE="${COMPOSE_FILE:-$REPO_ROOT/docker-compose.prod.yml}"
INIT_SQL="$REPO_ROOT/deploy/postgres/init/01-databases.sql"
BACKUP_SCRIPT="$REPO_ROOT/scripts/backup-postgres.sh"

cd "$REPO_ROOT"

echo "=== Deployment invariant checks ==="
echo "Compose file: $COMPOSE_FILE"

# ---------------------------------------------------------------------------
# 1. Parse docker-compose.prod.yml and assert topology invariants.
# ---------------------------------------------------------------------------

if ! command -v python3 >/dev/null 2>&1; then
    echo "Error: python3 is required for compose parsing" >&2
    exit 1
fi

python3 - "$COMPOSE_FILE" <<'PY'
import sys
import yaml

compose_file = sys.argv[1]
with open(compose_file) as f:
    data = yaml.safe_load(f)

services = data.get("services", {})
volumes = data.get("volumes", {})
networks = data.get("networks", {})

errors = []

def has_limits(svc):
    return "mem_limit" in svc and "cpus" in svc

def has_log_rotation(svc):
    log = svc.get("logging", {})
    opts = log.get("options", {})
    return (
        log.get("driver") == "json-file"
        and "max-size" in opts
        and "max-file" in opts
    )

def has_healthcheck(svc):
    return "healthcheck" in svc

for name, svc in services.items():
    if svc.get("network_mode") == "host":
        errors.append(f"{name} uses network_mode: host")

    if name != "caddy" and "ports" in svc:
        errors.append(f"{name} publishes ports; only Caddy should be public")

    if not has_limits(svc):
        errors.append(f"{name} is missing mem_limit or cpus")

    if not has_log_rotation(svc):
        errors.append(f"{name} is missing json-file log rotation")

    if not has_healthcheck(svc):
        errors.append(f"{name} is missing a healthcheck")

if "pad" not in networks or networks["pad"].get("driver") != "bridge":
    errors.append("Expected a private 'pad' bridge network")

expected_volumes = {"postgres_data", "redis_data", "caddy_data", "caddy_config"}
missing = expected_volumes - set(volumes.keys())
if missing:
    errors.append(f"Missing volumes: {sorted(missing)}")

if errors:
    print("Compose invariant failures:", file=sys.stderr)
    for e in errors:
        print(f"  - {e}", file=sys.stderr)
    sys.exit(1)

print("Compose invariants OK")
PY

# ---------------------------------------------------------------------------
# 2. PostgreSQL init script contains the three service databases.
# ---------------------------------------------------------------------------

if [[ ! -f "$INIT_SQL" ]]; then
    echo "Error: PostgreSQL init script not found: $INIT_SQL" >&2
    exit 1
fi

for db in pad keycloak coder; do
    if ! grep -qi "CREATE DATABASE.*$db" "$INIT_SQL"; then
        echo "Error: init script does not create '$db' database" >&2
        exit 1
    fi
done
echo "PostgreSQL init databases OK"

# ---------------------------------------------------------------------------
# 3. Caddy certificate persistence volume exists.
# ---------------------------------------------------------------------------

if ! grep -qE '^\s*caddy_data:' "$COMPOSE_FILE"; then
    echo "Error: caddy_data volume not defined; certificate persistence missing" >&2
    exit 1
fi
echo "Caddy certificate persistence volume OK"

# ---------------------------------------------------------------------------
# 4. Backup script produces one dump per database when the stack is running.
# ---------------------------------------------------------------------------

if [[ ! -x "$BACKUP_SCRIPT" ]]; then
    chmod +x "$BACKUP_SCRIPT" || true
fi

if ! command -v docker compose >/dev/null 2>&1; then
    echo "Skipping backup check: docker compose is not available"
elif ! docker compose ps --services --status running 2>/dev/null | grep -qx 'postgres'; then
    echo "Skipping backup check: postgres service is not running"
else
    BACKUP_DIR="$REPO_ROOT/.tmp-backup-check"
    rm -rf "$BACKUP_DIR"
    mkdir -p "$BACKUP_DIR"
    trap 'rm -rf "$BACKUP_DIR"' EXIT

    BACKUP_DIR="$BACKUP_DIR" "$BACKUP_SCRIPT"

    expected=(pad keycloak coder)
    missing=()
    for db in "${expected[@]}"; do
        if ! ls "$BACKUP_DIR"/${db}_*.sql.gz >/dev/null 2>&1; then
            missing+=("$db")
        fi
    done
    if [[ ${#missing[@]} -gt 0 ]]; then
        echo "Error: backup script did not produce dumps for: ${missing[*]}" >&2
        exit 1
    fi
    echo "Backup script OK (${#expected[@]} dumps)"
fi

echo "=== All deployment checks passed ==="
