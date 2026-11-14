#!/usr/bin/env bash
set -euo pipefail

# Restore all three service PostgreSQL databases from custom-format dumps.
#
# Usage:
#   ./scripts/restore-postgres.sh [--drill] [--keep] [pad_dump] [keycloak_dump] [coder_dump]
#
# Without --drill the dumps are restored into the running production/test stack.
# With --drill a fresh postgres container and volume are used so production data
# is not touched.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT_DIR/.env}"
COMPOSE_FILE="${COMPOSE_FILE:-$ROOT_DIR/docker-compose.prod.yml}"
BACKUP_DIR="${BACKUP_DIR:-$ROOT_DIR/backups}"
DRILL_PROJECT="pad-restore-drill"
DRILL_CONTAINER="pad-postgres-drill"
DRILL_VOLUME="postgres_drill_data"
DRILL_IMAGE="${POSTGRES_IMAGE:-postgres:16}"

names=(pad keycloak coder)

cd "$ROOT_DIR"

if [[ -f "$ENV_FILE" ]]; then
    set -a
    # shellcheck source=/dev/null
    source "$ENV_FILE"
    set +a
fi

POSTGRES_USER="${POSTGRES_USER:-admin}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-}"
POSTGRES_DB="${POSTGRES_DB:-pad}"
KEYCLOAK_DB="${KEYCLOAK_DB:-keycloak}"
CODER_DB="${CODER_DB:-coder}"

drill=false
keep=false
args=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        --drill)
            drill=true
            shift
            ;;
        --keep)
            keep=true
            shift
            ;;
        -h|--help)
            cat <<'EOF'
Usage: scripts/restore-postgres.sh [--drill] [--keep] [pad_dump] [keycloak_dump] [coder_dump]

  --drill   Restore into a fresh isolated postgres volume (does not touch production).
  --keep    Leave the drill container/volume running after verification.
EOF
            exit 0
            ;;
        *)
            args+=("$1")
            shift
            ;;
    esac
done

latest_dump() {
    local db="$1"
    find "$BACKUP_DIR" -maxdepth 1 -type f -name "${db}_*.dump.gz" -printf '%T@ %p\n' 2>/dev/null | sort -rn | head -1 | cut -d' ' -f2-
}

resolve_dumps() {
    local i
    for i in 0 1 2; do
        if [[ -n "${args[$i]:-}" ]]; then
            echo "${args[$i]}"
        else
            latest_dump "${names[$i]}"
        fi
    done
}

verify_dump() {
    local file="$1"
    if [[ ! -f "$file" ]]; then
        echo "ERROR: dump not found: $file" >&2
        return 1
    fi
    echo "Verifying dump integrity: $file"
    if ! gunzip -c "$file" | docker run --rm -i "$DRILL_IMAGE" sh -c 'tmp=$(mktemp); cat > "$tmp"; pg_restore --list "$tmp" >/dev/null; rc=$?; rm -f "$tmp"; exit $rc'; then
        echo "ERROR: integrity check failed for $file" >&2
        return 1
    fi
    echo "Integrity OK: $file"
}

restore_to() {
    local target="$1"
    local db="$2"
    local file="$3"
    echo "Restoring database '$db' to $target"
    if [[ "$target" == "drill" ]]; then
        gunzip -c "$file" | docker exec -i "$DRILL_CONTAINER" pg_restore \
            -U "$POSTGRES_USER" -d "$db" --no-owner --no-privileges
    else
        docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" exec -T postgres psql \
            -U "$POSTGRES_USER" -d postgres -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$db' AND pid <> pg_backend_pid();" >/dev/null 2>&1 || true
        docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" exec -T postgres psql \
            -U "$POSTGRES_USER" -d postgres -c "DROP DATABASE IF EXISTS $db;" >/dev/null
        docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" exec -T postgres psql \
            -U "$POSTGRES_USER" -d postgres -c "CREATE DATABASE $db OWNER $POSTGRES_USER;" >/dev/null
        gunzip -c "$file" | docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" exec -T postgres pg_restore \
            -U "$POSTGRES_USER" -d "$db" --no-owner --no-privileges
    fi
}

verify_content() {
    local target="$1"
    local psql
    if [[ "$target" == "drill" ]]; then
        psql="docker exec -i $DRILL_CONTAINER psql -U $POSTGRES_USER -t -A"
    else
        psql="docker compose -f $COMPOSE_FILE --env-file $ENV_FILE exec -T postgres psql -U $POSTGRES_USER -t -A"
    fi

    echo "Verifying restored content..."

    local pad_users
    pad_users="$($psql -d "$POSTGRES_DB" -c 'SELECT COUNT(*) FROM pad_ws.users;' 2>/dev/null || true)"
    echo "  Pad users: ${pad_users:-unknown}"

    local pad_pads
    pad_pads="$($psql -d "$POSTGRES_DB" -c 'SELECT COUNT(*) FROM pad_ws.pads;' 2>/dev/null || true)"
    echo "  Pad pads: ${pad_pads:-unknown}"

    local realm_tables
    realm_tables="$($psql -d "$KEYCLOAK_DB" -c 'SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = '"'"'public'"'"';' 2>/dev/null || true)"
    echo "  Keycloak tables: ${realm_tables:-unknown}"

    local coder_tables
    coder_tables="$($psql -d "$CODER_DB" -c 'SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = '"'"'public'"'"';' 2>/dev/null || true)"
    echo "  Coder tables: ${coder_tables:-unknown}"
}

# ---------------------------------------------------------------------------
# Resolve and verify dumps.
# ---------------------------------------------------------------------------
mapfile -t dumps < <(resolve_dumps)

for i in 0 1 2; do
    if [[ -z "${dumps[$i]:-}" ]]; then
        echo "ERROR: could not find a dump for ${names[$i]} in $BACKUP_DIR" >&2
        exit 1
    fi
done

for file in "${dumps[@]}"; do
    verify_dump "$file"
done

# ---------------------------------------------------------------------------
# Drill mode: start a fresh postgres container.
# ---------------------------------------------------------------------------
if [[ "$drill" == true ]]; then
    echo "Starting restore drill with isolated volume..."
    docker rm -f "$DRILL_CONTAINER" >/dev/null 2>&1 || true
    docker volume rm -f "$DRILL_VOLUME" >/dev/null 2>&1 || true
    docker volume create "$DRILL_VOLUME" >/dev/null
    docker run -d --name "$DRILL_CONTAINER" \
        -e POSTGRES_USER="$POSTGRES_USER" \
        -e POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-postgres}" \
        -e POSTGRES_DB="$POSTGRES_DB" \
        -v "$DRILL_VOLUME:/var/lib/postgresql/data" \
        -v "$ROOT_DIR/deploy/postgres/init:/docker-entrypoint-initdb.d:ro" \
        "$DRILL_IMAGE" >/dev/null

    echo "Waiting for drill database to be ready..."
    for _ in $(seq 1 90); do
        if docker exec "$DRILL_CONTAINER" psql -U "$POSTGRES_USER" -d postgres -tc "SELECT 1 FROM pg_database WHERE datname='pad'" | grep -q 1 && \
           docker exec "$DRILL_CONTAINER" psql -U "$POSTGRES_USER" -d postgres -tc "SELECT 1 FROM pg_database WHERE datname='keycloak'" | grep -q 1 && \
           docker exec "$DRILL_CONTAINER" psql -U "$POSTGRES_USER" -d postgres -tc "SELECT 1 FROM pg_database WHERE datname='coder'" | grep -q 1; then
            break
        fi
        sleep 1
    done

    for i in 0 1 2; do
        restore_to drill "${names[$i]}" "${dumps[$i]}"
    done

    verify_content drill

    if [[ "$keep" == true ]]; then
        echo "Drill container kept: $DRILL_CONTAINER (volume: $DRILL_VOLUME)"
    else
        echo "Stopping and removing drill container/volume..."
        docker rm -f "$DRILL_CONTAINER" >/dev/null
        docker volume rm -f "$DRILL_VOLUME" >/dev/null
    fi
    echo "Restore drill complete."
    exit 0
fi

# ---------------------------------------------------------------------------
# Normal restore into the running stack.
# ---------------------------------------------------------------------------
echo "Restoring into the running stack..."
for i in 0 1 2; do
    restore_to stack "${names[$i]}" "${dumps[$i]}"
done
verify_content stack
echo "Restore complete."
