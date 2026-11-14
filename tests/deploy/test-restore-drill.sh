#!/usr/bin/env bash
set -euo pipefail

# Verify the restore drill uses an isolated volume and does not touch production.

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RESTORE_SCRIPT="$REPO_ROOT/scripts/restore-postgres.sh"
BACKUP_DIR="$(mktemp -d -t restore-drill-backups-XXXXXX)"
TEST_CONTAINER="pad-test-postgres"
TEST_VOLUME="pad_test_postgres_data"
POSTGRES_IMAGE="postgres:16"
POSTGRES_USER="testadmin"
POSTGRES_PASSWORD="testpass"

cd "$REPO_ROOT"

echo "=== Restore drill tests ==="

# Clean up any leftover test container/volume.
docker rm -f "$TEST_CONTAINER" >/dev/null 2>&1 || true
docker volume rm -f "$TEST_VOLUME" >/dev/null 2>&1 || true

# Start a temporary postgres container with the init script.
docker run -d --name "$TEST_CONTAINER" \
    -e POSTGRES_USER="$POSTGRES_USER" \
    -e POSTGRES_PASSWORD="$POSTGRES_PASSWORD" \
    -e POSTGRES_DB="pad" \
    -v "$TEST_VOLUME:/var/lib/postgresql/data" \
    -v "$REPO_ROOT/deploy/postgres/init:/docker-entrypoint-initdb.d:ro" \
    "$POSTGRES_IMAGE" >/dev/null

# Wait for readiness and for the init script to finish creating databases.
for _ in $(seq 1 90); do
    if docker exec "$TEST_CONTAINER" psql -U "$POSTGRES_USER" -d pad -c 'SELECT 1' >/dev/null 2>&1 && \
       docker exec "$TEST_CONTAINER" psql -U "$POSTGRES_USER" -d keycloak -c 'SELECT 1' >/dev/null 2>&1 && \
       docker exec "$TEST_CONTAINER" psql -U "$POSTGRES_USER" -d coder -c 'SELECT 1' >/dev/null 2>&1; then
        break
    fi
    sleep 1
done

# Create simple content in each database so the dumps are non-empty.
docker exec "$TEST_CONTAINER" psql -U "$POSTGRES_USER" -d pad -c "CREATE SCHEMA pad_ws; CREATE TABLE pad_ws.users (id serial PRIMARY KEY); INSERT INTO pad_ws.users DEFAULT VALUES;" >/dev/null
docker exec "$TEST_CONTAINER" psql -U "$POSTGRES_USER" -d keycloak -c "CREATE TABLE dummy (id serial PRIMARY KEY); INSERT INTO dummy DEFAULT VALUES;" >/dev/null
docker exec "$TEST_CONTAINER" psql -U "$POSTGRES_USER" -d coder -c "CREATE TABLE dummy (id serial PRIMARY KEY); INSERT INTO dummy DEFAULT VALUES;" >/dev/null

# Dump each database.
timestamp="$(date +%Y%m%d_%H%M%S)"
for db in pad keycloak coder; do
    docker exec "$TEST_CONTAINER" pg_dump -Fc -U "$POSTGRES_USER" -d "$db" | gzip > "$BACKUP_DIR/${db}_${timestamp}.dump.gz"
done

# Remove the source container so the drill cannot accidentally use it.
docker rm -f "$TEST_CONTAINER" >/dev/null
docker volume rm -f "$TEST_VOLUME" >/dev/null

# Run the restore drill.
restore_out="$(BACKUP_DIR="$BACKUP_DIR" POSTGRES_USER="$POSTGRES_USER" POSTGRES_PASSWORD="$POSTGRES_PASSWORD" \
    POSTGRES_DB="pad" KEYCLOAK_DB="keycloak" CODER_DB="coder" \
    bash "$RESTORE_SCRIPT" --drill 2>&1)" || true
if ! echo "$restore_out" | grep -q 'Restore drill complete'; then
    echo "FAIL: restore drill exited non-zero" >&2
    echo "$restore_out" >&2
    exit 1
fi

# Ensure the drill container/volume were cleaned up.
if docker ps -a --format '{{.Names}}' | grep -qx 'pad-postgres-drill'; then
    echo "FAIL: drill container was not removed" >&2
    exit 1
fi
if docker volume ls -q | grep -qx 'postgres_drill_data'; then
    echo "FAIL: drill volume was not removed" >&2
    exit 1
fi

echo "Restore drill isolated and complete OK"

# Verify a corrupt dump fails integrity check.
corrupt="$BACKUP_DIR/pad_corrupt.dump.gz"
echo "not-valid" | gzip > "$corrupt"
if BACKUP_DIR="$BACKUP_DIR" POSTGRES_USER="$POSTGRES_USER" bash "$RESTORE_SCRIPT" --drill "$corrupt" "$BACKUP_DIR/keycloak_${timestamp}.dump.gz" "$BACKUP_DIR/coder_${timestamp}.dump.gz" >/dev/null 2>&1; then
    echo "FAIL: corrupt dump was accepted by restore" >&2
    exit 1
fi
echo "Corrupt dump restore rejection OK"

rm -rf "$BACKUP_DIR"
echo "=== Restore drill tests passed ==="
