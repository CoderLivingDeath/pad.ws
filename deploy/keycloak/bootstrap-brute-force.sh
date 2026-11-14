#!/usr/bin/env bash
set -euo pipefail

# Idempotently enable Keycloak brute-force protection for the Pad realm.
#
# realm-export.json only applies on a fresh Keycloak database. On an existing
# deployment (or after a container recreate that preserves the database) run
# this script to enforce the same limits.
#
# Environment variables:
#   KEYCLOAK_ADMIN             Keycloak master realm admin user (default: admin)
#   KEYCLOAK_ADMIN_PASSWORD    Required master realm admin password
#   OIDC_REALM                 Realm to configure (default: pad)
#
# Example:
#   KEYCLOAK_ADMIN_PASSWORD='...' ./deploy/keycloak/bootstrap-brute-force.sh

ADMIN="${KEYCLOAK_ADMIN:-admin}"
ADMIN_PASS="${KEYCLOAK_ADMIN_PASSWORD:?KEYCLOAK_ADMIN_PASSWORD is required}"
REALM="${OIDC_REALM:-pad}"

# These values must stay in sync with deploy/keycloak/realm-export.json.
SETTINGS=(
  "bruteForceProtected=true"
  "permanentLockout=false"
  "maxFailureWaitSeconds=900"
  "minimumQuickLoginWaitSeconds=60"
  "waitIncrementSeconds=60"
  "quickLoginCheckMilliSeconds=1000"
  "maxDeltaTimeSeconds=300"
  "failureFactor=5"
)

kcadm() {
  docker compose exec -T keycloak /opt/keycloak/bin/kcadm.sh "$@"
}

kcadm config credentials \
  --server http://localhost:8080 \
  --realm master \
  --user "$ADMIN" \
  --password "$ADMIN_PASS" >/dev/null

# Build the -s flags for the update command.
args=()
for setting in "${SETTINGS[@]}"; do
  args+=(-s "$setting")
done

kcadm update "realms/$REALM" "${args[@]}"

echo "Brute-force protection enabled for realm '$REALM'."
