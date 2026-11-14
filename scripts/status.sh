#!/usr/bin/env bash
set -euo pipefail

# Operational status baseline.
# Usage: scripts/status.sh
# Checks service health, image digests, certificate state, backup age and
# Coder key age. Exits non-zero when a check fails.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT_DIR/.env}"
COMPOSE_FILE="${COMPOSE_FILE:-$ROOT_DIR/docker-compose.prod.yml}"
COMPOSE_TEST_FILE="${COMPOSE_TEST_FILE:-$ROOT_DIR/compose.test.yml}"
BACKUP_DIR="${BACKUP_DIR:-$ROOT_DIR/backups}"
BACKUP_RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-}"
CODER_KEY_WARNING_DAYS="${CODER_KEY_WARNING_DAYS:-6}"
CODER_KEY_MAX_DAYS="${CODER_KEY_MAX_DAYS:-7}"
CERT_WARNING_DAYS="${CERT_WARNING_DAYS:-14}"

cd "$ROOT_DIR"

if [[ -f "$ENV_FILE" ]]; then
    set -a
    # shellcheck source=/dev/null
    source "$ENV_FILE"
    set +a
fi

COMPOSE="docker compose -f $COMPOSE_FILE"
if [[ -f "$COMPOSE_TEST_FILE" ]] && [[ "${USE_TEST_COMPOSE:-false}" == "true" ]]; then
    COMPOSE="docker compose -f $COMPOSE_FILE -f $COMPOSE_TEST_FILE"
fi
COMPOSE="$COMPOSE --env-file $ENV_FILE"

failures=0
warn() { echo "WARN: $1" >&2; }
fail() { echo "FAIL: $1" >&2; failures=$((failures + 1)); }
pass() { echo "OK:   $1"; }

# ---------------------------------------------------------------------------
# 1. Container health
# ---------------------------------------------------------------------------
services=(caddy pad postgres redis keycloak coder)
for service in "${services[@]}"; do
    container="$($COMPOSE ps -q "$service" 2>/dev/null || true)"
    if [[ -z "$container" ]]; then
        fail "$service is not running"
        continue
    fi
    status="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container" 2>/dev/null || true)"
    if [[ "$status" == "healthy" ]]; then
        pass "$service container is healthy"
    elif [[ "$status" == "running" || "$status" == "started" ]]; then
        warn "$service container is running but has no health status"
    else
        fail "$service container status is $status"
    fi
done

# ---------------------------------------------------------------------------
# 2. Image digests
# ---------------------------------------------------------------------------
for service in caddy pad postgres redis keycloak coder; do
    container="$($COMPOSE ps -q "$service" 2>/dev/null || true)"
    if [[ -z "$container" ]]; then
        continue
    fi
    digest="$(docker inspect -f '{{.Image}}' "$container" 2>/dev/null || true)"
    image="$(docker inspect -f '{{.Config.Image}}' "$container" 2>/dev/null || true)"
    echo "INFO: $service image=$image digest=$digest"
done

# ---------------------------------------------------------------------------
# 3. Coder key age
# ---------------------------------------------------------------------------
if [[ -z "${CODER_API_KEY_CREATED_AT:-}" ]]; then
    warn "CODER_API_KEY_CREATED_AT is not set; key age is unknown"
else
    if command -v python3 >/dev/null 2>&1; then
        age_seconds="$(python3 - "$CODER_API_KEY_CREATED_AT" "$CODER_KEY_MAX_DAYS" <<'PY'
import sys
from datetime import datetime, timezone, timedelta
created = datetime.fromisoformat(sys.argv[1].replace('Z', '+00:00'))
now = datetime.now(timezone.utc)
print(int((now - created).total_seconds()))
PY
)"
        age_days=$((age_seconds / 86400))
        if [[ "$age_days" -ge "$CODER_KEY_MAX_DAYS" ]]; then
            fail "Coder API key is $age_days days old (max $CODER_KEY_MAX_DAYS)"
        elif [[ "$age_days" -ge "$CODER_KEY_WARNING_DAYS" ]]; then
            warn "Coder API key is $age_days days old (rotate before $CODER_KEY_MAX_DAYS days)"
        else
            pass "Coder API key is $age_days days old"
        fi
    else
        warn "python3 is not available; cannot compute Coder key age"
    fi
fi

# ---------------------------------------------------------------------------
# 4. Certificate expiry
# ---------------------------------------------------------------------------
if [[ -n "${PAD_DOMAIN:-}" ]] && command -v openssl >/dev/null 2>&1; then
    if curl -fsS --max-time 5 "https://$PAD_DOMAIN" >/dev/null 2>&1; then
        expiry_str="$(printf 'Q\n' | openssl s_client -servername "$PAD_DOMAIN" -connect "$PAD_DOMAIN:443" 2>/dev/null |
            openssl x509 -noout -enddate 2>/dev/null | cut -d= -f2- || true)"
        if [[ -n "$expiry_str" ]] && command -v python3 >/dev/null 2>&1; then
            expiry_days="$(python3 - "$expiry_str" "$CERT_WARNING_DAYS" <<'PY'
import sys
from datetime import datetime, timezone
expiry = datetime.strptime(sys.argv[1], '%b %d %H:%M:%S %Y %Z')
expiry = expiry.replace(tzinfo=timezone.utc)
now = datetime.now(timezone.utc)
print(max(0, int((expiry - now).total_seconds() / 86400)))
PY
)"
            if [[ "$expiry_days" -le 0 ]]; then
                fail "TLS certificate for $PAD_DOMAIN has expired"
            elif [[ "$expiry_days" -le "$CERT_WARNING_DAYS" ]]; then
                warn "TLS certificate for $PAD_DOMAIN expires in $expiry_days days"
            else
                pass "TLS certificate for $PAD_DOMAIN expires in $expiry_days days"
            fi
        fi
    else
        warn "cannot reach https://$PAD_DOMAIN to check certificate expiry"
    fi
fi

# ---------------------------------------------------------------------------
# 5. Last backup age
# ---------------------------------------------------------------------------
if [[ ! -d "$BACKUP_DIR" ]]; then
    warn "backup directory does not exist: $BACKUP_DIR"
else
    latest="$(find "$BACKUP_DIR" -maxdepth 1 -type f -name '*.sql.gz' -printf '%T@ %p\n' 2>/dev/null | sort -rn | head -1 | cut -d' ' -f2- || true)"
    if [[ -z "$latest" ]]; then
        fail "no backups found in $BACKUP_DIR"
    else
        age_minutes="$(python3 -c "import os,time; print(int((time.time()-os.path.getmtime('$latest'))/60))" 2>/dev/null || true)"
        age_hours=$((age_minutes / 60))
        if [[ -n "$BACKUP_RETENTION_DAYS" ]] && [[ "$BACKUP_RETENTION_DAYS" =~ ^[0-9]+$ ]]; then
            retention_minutes=$((BACKUP_RETENTION_DAYS * 1440))
            if [[ "$age_minutes" -gt "$retention_minutes" ]]; then
                fail "latest backup is older than retention (${BACKUP_RETENTION_DAYS} days): $latest"
            else
                pass "latest backup is ${age_hours}h old: $latest"
            fi
        else
            pass "latest backup is ${age_hours}h old: $latest"
        fi
    fi
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
if [[ "$failures" -gt 0 ]]; then
    echo "Status check failed with $failures failure(s)" >&2
    exit 1
fi

echo "Status OK"
