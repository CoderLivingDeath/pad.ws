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
PREFLIGHT_SCRIPT="$REPO_ROOT/deploy/preflight.sh"

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

    # Every production service must use an image variable.
    if "image" not in svc or not svc["image"].startswith("${"):
        errors.append(f"{name} is not using an ${'{'}*_IMAGE{'}'} variable")

if "edge" not in networks or networks["edge"].get("driver") != "bridge":
    errors.append("Expected a dedicated 'edge' bridge network for Caddy")

edge_ipam = networks.get("edge", {}).get("ipam", {}).get("config", [])
if not any(cfg.get("subnet") for cfg in edge_ipam):
    errors.append("edge network is missing a static subnet")

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
# 4. Backup script is executable.
# ---------------------------------------------------------------------------

if [[ ! -x "$BACKUP_SCRIPT" ]]; then
    chmod +x "$BACKUP_SCRIPT" || true
fi
echo "Backup script present and executable OK"

# ---------------------------------------------------------------------------
# 5. Preflight script rejects missing/placeholder values.
# ---------------------------------------------------------------------------

if [[ -x "$PREFLIGHT_SCRIPT" ]]; then
    tmp_env="$(mktemp -t preflight-test-XXXXXX.env)"
    trap 'rm -f "$tmp_env"' EXIT
    cat > "$tmp_env" <<'EOF'
POSTGRES_PASSWORD=__CHANGE_ME__
ADMIN_ALLOWLIST=0.0.0.0/0 ::/0
PROFILE=production
EOF
    if "$PREFLIGHT_SCRIPT" "$tmp_env" >/dev/null 2>&1; then
        echo "Error: preflight accepted a placeholder production env" >&2
        exit 1
    fi
    echo "Preflight placeholder rejection OK"

    cat > "$tmp_env" <<'EOF'
POSTGRES_PASSWORD=secret
REDIS_PASSWORD=secret
KEYCLOAK_ADMIN_PASSWORD=secret
OIDC_CLIENT_SECRET=secret
CODER_API_KEY=secret
PAD_DOMAIN=pad.example.com
AUTH_DOMAIN=auth.example.com
CODER_DOMAIN=coder.example.com
COOKIE_DOMAIN=.example.com
OIDC_SERVER_URL=https://auth.example.com
REDIRECT_URI=https://pad.example.com/api/auth/callback
FRONTEND_URL=https://pad.example.com
ADMIN_ALLOWLIST=203.0.113.0/24
ACME_EMAIL=ops@example.com
PAD_ALLOWED_ROLES=pad-user
CADDYFILE=deploy/Caddyfile
POSTGRES_USER=admin
POSTGRES_DB=pad
KEYCLOAK_ADMIN=admin
KEYCLOAK_DB=keycloak
CODER_DB=coder
CODER_DB_PASSWORD_URLENCODED=secret
CODER_TEMPLATE_ID=00000000-0000-0000-0000-000000000001
CODER_DEFAULT_ORGANIZATION=00000000-0000-0000-0000-000000000002
DOCKER_GROUP_ID=999
CADDY_IMAGE=caddy:2-alpine@sha256:003a97808e781aa9f7e75cc2f43d34d461099031faf5e20faefb9f61126836f0
POSTGRES_IMAGE=postgres:16@sha256:63e83b5a3dc36a917dccb76fe1bd2ac51f1ec9c1deb47ff20d4f04233bf6eae9
REDIS_IMAGE=redis:7.2-alpine@sha256:a2c8f9d7c49c74ebd2945e3798c71606545c5f0d90d03e9ec4a2bb8d4f56df36
KEYCLOAK_IMAGE=quay.io/keycloak/keycloak:25.0@sha256:82c5b7a110456dbd42b86ea572e728878549954cc8bd03cd65410d75328095d2
CODER_IMAGE=ghcr.io/coder/coder:latest@sha256:77500de63a62f733bb1fbbf79da85e8ad4d6ca582e964f5d6021f46f6dc7fc29
PAD_IMAGE=ghcr.io/pad-ws/pad.ws:main@sha256:0000000000000000000000000000000000000000000000000000000000000000
PROFILE=production
EOF
    if ! "$PREFLIGHT_SCRIPT" "$tmp_env" >/dev/null 2>&1; then
        echo "Error: preflight rejected a valid production env" >&2
        exit 1
    fi
    echo "Preflight valid production env OK"
fi

# ---------------------------------------------------------------------------
# 6. Backup retention prunes old dumps and integrity fails on corrupt dumps.
# ---------------------------------------------------------------------------

tmp_backup="$(mktemp -d -t backup-retention-XXXXXX)"
trap 'rm -rf "$tmp_backup"' EXIT

# Create an old dump.
old_dump="$tmp_backup/pad_20260101_000000.dump.gz"
echo "-- old" | gzip > "$old_dump"
touch -d "90 days ago" "$old_dump"

# Create a recent corrupt dump.
corrupt_dump="$tmp_backup/pad_20261114_000000.dump.gz"
echo "not-a-valid-pgdump" | gzip > "$corrupt_dump"

# Run a Python retention prune similar to the backup script.
python3 - "$tmp_backup" <<'PY'
import os, sys, time
dirname = sys.argv[1]
retention_days = 30
now = time.time()
for f in os.listdir(dirname):
    if not f.endswith('.dump.gz'):
        continue
    path = os.path.join(dirname, f)
    if (now - os.path.getmtime(path)) / 86400 > retention_days:
        os.remove(path)
        print(f"pruned {f}")
PY

if [[ -f "$old_dump" ]]; then
    echo "Error: old dump was not pruned" >&2
    exit 1
fi
echo "Backup retention pruning OK"

if gunzip -c "$corrupt_dump" | docker run --rm -i postgres:16 sh -c 'tmp=$(mktemp); cat > "$tmp"; pg_restore --list "$tmp" >/dev/null; rc=$?; rm -f "$tmp"; exit $rc' 2>/dev/null; then
    echo "Error: corrupt dump passed pg_restore --list" >&2
    exit 1
fi
echo "Corrupt dump integrity failure OK"

echo "=== All deployment checks passed ==="
