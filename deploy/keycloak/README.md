# Keycloak configuration

This directory contains the **test-only** Keycloak realm export used for local
`*.pad.test` acceptance testing. Production Keycloak should be configured with
the same realm and client settings, but the export file itself is intended for
the local/test profile only.

## Files

- `realm-export.json` — committed realm export for the `pad` realm, imported
  automatically when Keycloak starts with `KC_IMPORT` or a test bootstrap. It
  is **not** used in production.

## Production realm setup

In production, create or import a realm named `pad` with the following
settings:

- **Realm name:** `pad`
- **Registration allowed:** disabled (`registrationAllowed = false`)
- **Email verification:** required (`verifyEmail = true`)
- **Login with email allowed:** `true`

### Confidential client `pad`

Create a confidential OIDC client named `pad`:

| Setting | Value |
| --- | --- |
| Client ID | `pad` |
| Client authenticator | Client secret |
| Standard flow | enabled |
| Implicit flow | disabled |
| Direct access grants | disabled |
| Service accounts | disabled |
| Public client | no |

**Exact redirect URIs (no wildcards):**

```
https://pad.pad.test/api/auth/callback
https://coder.pad.test/api/v2/users/oidc/callback
```

**Exact web origins (no wildcards):**

```
https://pad.pad.test
https://coder.pad.test
```

**Audience mapper:** add a protocol mapper named `pad-audience` of type
"Audience" with:

- Included Client Audience: `pad`
- Add to access token: `true`
- Add to ID token: `false`
- Add to userinfo: `false`

This ensures the access token contains `aud` equal to the `pad` client ID, which
Pad validates during callback.

When the real production domains differ from `*.pad.test`, update the redirect
URIs and web origins to match `https://${PAD_DOMAIN}/api/auth/callback`,
`https://${CODER_DOMAIN}/api/v2/users/oidc/callback`, and the corresponding
exact origins.

## Brute-force protection

The `pad` realm enables Keycloak brute-force detection with the following
limits (see `realm-export.json`):

| Setting | Value |
| --- | --- |
| `bruteForceProtected` | `true` |
| `failureFactor` | `5` |
| `maxDeltaTimeSeconds` | `300` |
| `minimumQuickLoginWaitSeconds` | `60` |
| `waitIncrementSeconds` | `60` |
| `maxFailureWaitSeconds` | `900` |
| `permanentLockout` | `false` |

These settings apply automatically when the realm is imported on a fresh
Keycloak database. For an existing database, or after recreating the Keycloak
container while preserving its volume, re-run the idempotent bootstrap script:

```bash
KEYCLOAK_ADMIN_PASSWORD='...' ./deploy/keycloak/bootstrap-brute-force.sh
```

The script updates the realm in place and is safe to run multiple times.

## Realm roles

Two realm roles are used:

| Role | Purpose |
| --- | --- |
| `pad-user` | Required to receive a Pad session. `PAD_ALLOWED_ROLES=pad-user` in `.env`. |
| `admin` | Additional realm role used by Caddy to gate Keycloak `/admin*` paths. |

`pad-user` grants basic Pad access. `admin` is an **additional** realm role; a
user must have `pad-user` (or whatever `PAD_ALLOWED_ROLES` requires) **and**
`admin` to reach Keycloak administrative paths through Caddy.

The test export grants:

- `admin` user → `pad-user` and `admin`
- `user` user → `pad-user`
- `unprovisioned` user → no Pad roles

## Test users

The committed export defines three test users. All passwords are **test-only**
and must be replaced or removed in production.

| Username | Roles | Password | Notes |
| --- | --- | --- | --- |
| `admin` | `pad-user`, `admin` | `Password123!` | Pad admin and Keycloak console access |
| `user` | `pad-user` | `Password123!` | Regular Pad user |
| `unprovisioned` | none | `Password123!` | Used to verify `403` for unprovisioned users |

All three users have `emailVerified = true`.

## Two-layer administrative model

Keycloak has **two separate authorization layers** in this deployment:

1. **Pad authorization** — enforced by Caddy via `forward_auth` to Pad. The
   `admin` realm role is translated into the `X-Pad-Admin: true` response header,
   and Caddy uses that header (plus the `ADMIN_ALLOWLIST`) to decide whether to
   proxy `/admin*` on the Keycloak host.

2. **Keycloak administrative permissions** — enforced by Keycloak itself. Once
   Caddy forwards a request to Keycloak `/admin*`, Keycloak checks whether the
   authenticated user has the Keycloak-internal `realm-admin` or equivalent
   roles. These permissions are managed inside Keycloak under **Realm settings**
→ **Roles** → **Realm-management**.

A user with only the Pad `admin` realm role but no Keycloak realm-management
role may pass Caddy but will still see limited functionality in the Keycloak
admin console. Conversely, a Keycloak master realm admin or a user with
Keycloak realm-management roles is **not automatically** a Pad admin: Caddy
still requires the `admin` realm role and an allowed source IP.

### Break-glass access

If Pad is unavailable and you need to reach Keycloak admin directly:

1. SSH to the host.
2. Run a local port forward, for example:
   `ssh -L 8080:localhost:8080 user@host` (if Keycloak exposes its health port
   locally) or use `docker exec` into the Keycloak container.
3. Log in with the Keycloak master realm credentials (`KEYCLOAK_ADMIN` /
`KEYCLOAK_ADMIN_PASSWORD`) or a user that has Keycloak realm-management roles.

This path bypasses the Pad gate by design and should be restricted to the
operator.

## Session revocation

When a user logs out of Pad:

1. `/api/auth/logout` deletes the Redis session key (`session:{session_id}`)
   and publishes a revocation signal so any open Pad WebSocket closes
   immediately.
2. Caddy's next `forward_auth` request for that cookie receives `401` and
   denies access to Pad, Coder browser surfaces, and Keycloak `/admin*`.
3. The logout response also returns a `coder_logout_url` that the frontend
   loads in a hidden iframe. Caddy's `/__pad/logout` route clears every
   documented Coder cookie on the Coder host:
   `coder_session_token`, `coder_oauth_state`, `oauth_state`,
   `oauth_redirect`, `oauth_pkce_verifier` and `csrf_token`. This ensures a
   second Pad user on the same browser does not inherit the first user's Coder
   session.

To revoke **all** Pad sessions immediately, delete every `session:*` key from
Redis:

```bash
docker compose exec redis redis-cli -a "$REDIS_PASSWORD" --scan --pattern 'session:*' | \
  xargs -r docker compose exec -T redis redis-cli -a "$REDIS_PASSWORD" del
```

This is documented in the deployment runbook and applies to both production and
local test modes.
