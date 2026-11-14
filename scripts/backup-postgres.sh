#!/usr/bin/env bash
set -euo pipefail

# Backup all service PostgreSQL databases to timestamped compressed custom-format dumps.
#
# Usage:
#   POSTGRES_USER=postgres ./scripts/backup-postgres.sh
#   BACKUP_DATABASES="pad keycloak" BACKUP_RETENTION_DAYS=7 ./scripts/backup-postgres.sh
#
# Restore with scripts/restore-postgres.sh.

cd "$(dirname "${BASH_SOURCE[0]}")/.."

BACKUP_DIR="${BACKUP_DIR:-./backups}"
BACKUP_DATABASES="${BACKUP_DATABASES:-pad keycloak coder}"
POSTGRES_USER="${POSTGRES_USER:-postgres}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"

compose() {
    docker compose -f "$COMPOSE_FILE" "$@"
}

mkdir -m 700 -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"

timestamp="$(date +%Y%m%d_%H%M%S)"

if ! compose version >/dev/null 2>&1; then
    echo "Error: docker compose is not available" >&2
    exit 1
fi

if ! compose ps --services --status running 2>/dev/null | grep -qx 'postgres'; then
    echo "Error: postgres service is not running" >&2
    exit 1
fi

read -ra databases <<< "$BACKUP_DATABASES"
created=()
failed=()

for db in "${databases[@]}"; do
    out="${BACKUP_DIR}/${db}_${timestamp}.dump.gz"
    echo "Backing up database: $db"
    if compose exec -T postgres sh -c 'pg_dump -Fc -U "$POSTGRES_USER" -d "$1"' _ "$db" | gzip > "$out"; then
        chmod 600 "$out"
        size="$(du -h "$out" | cut -f1)"
        echo "Created: $out ($size)"
        if gunzip -c "$out" | compose exec -T postgres sh -c 'tmp=$(mktemp); cat > "$tmp"; pg_restore --list "$tmp" >/dev/null; rc=$?; rm -f "$tmp"; exit $rc'; then
            echo "Integrity check OK: $out"
        else
            echo "Error: integrity check failed for $out" >&2
            failed+=("$db")
            rm -f "$out"
            continue
        fi
        created+=("$out")
    else
        echo "Error: backup failed for database: $db" >&2
        failed+=("$db")
        rm -f "$out"
    fi
done

if [[ ${#failed[@]} -gt 0 ]]; then
    echo "Error: failed to back up or verify: ${failed[*]}" >&2
    exit 1
fi

if [[ -n "$RETENTION_DAYS" ]] && [[ "$RETENTION_DAYS" =~ ^[0-9]+$ ]]; then
    echo "Pruning dumps older than $RETENTION_DAYS days in $BACKUP_DIR"
    for db in "${databases[@]}"; do
        find "$BACKUP_DIR" -maxdepth 1 -type f -name "${db}_*.dump.gz" -mtime "+$RETENTION_DAYS" -delete
    done
fi

echo "Backup complete: ${#created[@]} file(s)"
