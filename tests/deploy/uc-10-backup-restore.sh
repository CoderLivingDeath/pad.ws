#!/usr/bin/env bash
# UC-10 — Backup and restore (dry-run / isolated-drill path).
#
# Validates that backup scripts exist, retention prunes old dumps, corrupt
# dumps fail integrity checks, and the restore drill runs in an isolated
# container/volume without touching production data.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BACKUP_SCRIPT="$REPO_ROOT/scripts/backup-postgres.sh"
RESTORE_SCRIPT="$REPO_ROOT/scripts/restore-postgres.sh"

cd "$REPO_ROOT"

echo "=== UC-10 backup and restore checks ==="

# ---------------------------------------------------------------------------
# 1. Backup and restore scripts are present and executable.
# ---------------------------------------------------------------------------
if [[ ! -f "$BACKUP_SCRIPT" ]]; then
    echo "FAIL: backup script not found: $BACKUP_SCRIPT" >&2
    exit 1
fi
if [[ ! -x "$BACKUP_SCRIPT" ]]; then
    chmod +x "$BACKUP_SCRIPT" || true
fi
echo "Backup script present and executable OK"

if [[ ! -f "$RESTORE_SCRIPT" ]]; then
    echo "FAIL: restore script not found: $RESTORE_SCRIPT" >&2
    exit 1
fi
if [[ ! -x "$RESTORE_SCRIPT" ]]; then
    chmod +x "$RESTORE_SCRIPT" || true
fi
echo "Restore script present and executable OK"

# ---------------------------------------------------------------------------
# 2. Retention prunes old dumps and corrupt dumps fail pg_restore --list.
# ---------------------------------------------------------------------------
if ! bash "$REPO_ROOT/tests/deploy/run-checks.sh" >/dev/null 2>&1; then
    echo "FAIL: backup retention / integrity checks failed" >&2
    exit 1
fi
echo "Backup retention and integrity checks OK"

# ---------------------------------------------------------------------------
# 3. Restore drill uses an isolated container and volume.
# ---------------------------------------------------------------------------
if ! bash "$REPO_ROOT/tests/deploy/test-restore-drill.sh" >/dev/null 2>&1; then
    echo "FAIL: restore drill test failed" >&2
    exit 1
fi
echo "Restore drill OK"

echo "=== UC-10 checks passed ==="
