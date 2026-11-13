# Deployment Runbook

This document is the operator runbook for a single-VPS deployment of Pad with the Caddy authentication gateway. It covers Debian/Ubuntu hosts, public domains, the local `*.pad.test` acceptance profile, Keycloak/Coder bootstrap, backup/restore, rollback and the security model.

For day-to-day development use the `docker-compose.yml` host-networking stack; for anything reachable from the internet use `docker-compose.prod.yml` and this runbook.

## 1. Environment variable matrix

| Variable | Consumer | Production value | Local value |
| --- | --- | --- | --- |
| `PAD_DOMAIN` | Caddy, Pad, Keycloak, Coder | `pad.example.com` | `pad.pad.test` |
| `AUTH_DOMAIN` | Caddy, Keycloak | `auth.example.com` | `auth.pad.test` |
| `CODER_DOMAIN` | Caddy, Pad, Coder | `coder.example.com` | `coder.pad.test` |
| `COOKIE_DOMAIN` | Pad, Caddy | `.example.com` | `.pad.test` |
| `CADDYFILE` | Compose | `deploy/Caddyfile` | `deploy/Caddyfile.local` |
| `ACME_EMAIL` | Caddy | operator email | `local@pad.test` |
| `OIDC_SERVER_URL` | Pad, Coder, Keycloak | `https://auth.example.com` | `https://auth.pad.test` |
| `OIDC_INTERNAL_URL` | Pad | `http://keycloak:8080` (default: `OIDC_SERVER_URL`) | `http://keycloak:8080` |
| `REDIRECT_URI` | Pad | `https://pad.example.com/api/auth/callback` | `https://pad.pad.test/api/auth/callback` |
| `FRONTEND_URL` | Pad, Caddy | `https://pad.example.com` | `https://pad.pad.test` |
| `OIDC_REALM` | Pad, Coder, Keycloak | realm name | `pad` |
| `OIDC_CLIENT_ID` | Pad, Coder | client ID | `pad` |
| `OIDC_CLIENT_SECRET` | Pad, Coder | generated secret | `__CHANGE_ME__` |
| `POSTGRES_USER` | PostgreSQL, Keycloak, Coder, Pad | generated username | `admin` |
| `POSTGRES_PASSWORD` | PostgreSQL, Keycloak, Coder, Pad | generated password | `__CHANGE_ME__` |
| `POSTGRES_DB` | PostgreSQL, Pad | `pad` | `pad` |
| `POSTGRES_HOST` | Pad | `postgres` | `postgres` |
| `POSTGRES_PORT` | Pad | `5432` | `5432` |
| `REDIS_PASSWORD` | Redis, Pad | generated password | `__CHANGE_ME__` |
| `REDIS_HOST` | Pad | `redis` | `redis` |
| `REDIS_PORT` | Pad | `6379` | `6379` |
| `KEYCLOAK_ADMIN` | Keycloak | admin username | `admin` |
| `KEYCLOAK_ADMIN_PASSWORD` | Keycloak | generated password | `__CHANGE_ME__` |
| `KEYCLOAK_DB` | Keycloak | `keycloak` | `keycloak` |
| `CODER_API_KEY` | Pad | generated API key | `__CHANGE_ME__` |
| `CODER_URL` | Pad, Coder | `https://coder.example.com` | `https://coder.pad.test` |
| `CODER_INTERNAL_URL` | Pad | `http://coder:7080` (default: `CODER_URL`) | `http://coder:7080` |
| `CODER_TEMPLATE_ID` | Pad | template UUID | `__CHANGE_ME__` |
| `CODER_DEFAULT_ORGANIZATION` | Pad | organization UUID | `__CHANGE_ME__` |
| `CODER_WORKSPACE_NAME` | Pad | default workspace name | `ubuntu` |
| `CODER_DB` | Coder | `coder` | `coder` |
| `CODER_DB_PASSWORD_URLENCODED` | Coder | URL-encoded password | `__CHANGE_ME__` |
| `DOCKER_GROUP_ID` | Coder | host docker group ID | `__CHANGE_ME__` |
| `ADMIN_ALLOWLIST` | Caddy | operator CIDRs | `0.0.0.0/0 ::/0` |
| `PAD_ALLOWED_ROLES` | Pad | `pad-user` | `pad-user` |
| `SESSION_COOKIE_NAME` | Pad, Caddy | `session_id` | `session_id` |
| `TRUSTED_PROXY_IPS` | Pad | `*` or fixed Caddy IP | `*` |
| `API_WORKERS` | Pad | `1` | `1` |
| `STATIC_DIR` | Pad | `/app/frontend/dist` | `/app/frontend/dist` |
| `ASSETS_DIR` | Pad | `/app/frontend/dist/assets` | `/app/frontend/dist/assets` |

## 2. Session and token lifetimes

Pad's session layer uses three related lifetimes:

- **Access token lifetime**: dictated by Keycloak (`expires_in` in the token response). Pad caches the token in Redis and refreshes it when it is within 30 seconds of expiry.
- **Refresh token lifetime**: dictated by Keycloak (`refresh_expires_in`). It determines how long a Pad session can remain active without re-authentication. The Redis `session:{id}` key and the browser session cookie both use this value as their `Max-Age` / TTL.
- **Cookie lifetime**: the `session_id` cookie is set with `Max-Age` equal to the refresh lifetime so that the browser can silently re-authenticate through the Keycloak SSO session while the cookie is valid.

When the refresh lifetime ends, `/api/auth/verify` and `/api/auth/refresh` return `401` and the user must log in again. If the cookie expires while the Keycloak SSO session is still valid, the next navigation triggers a new OIDC login that re-authenticates silently and restores the Pad session.

## 3. Host prerequisites

Use a dedicated Debian or Ubuntu VPS. The production topology assumes a single host with a small, trusted group of users.

- **Docker Engine** and **Docker Compose plugin** (v2) installed.
- A non-root deployment user added to the `docker` group.
- **Firewall** allowing only:
  - SSH (TCP 22)
  - HTTP (TCP 80)
  - HTTPS (TCP 443)
  - HTTP/3 (UDP 443) if you want QUIC

Example with `ufw`:

```bash
sudo ufw default deny incoming
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow 443/udp
sudo ufw enable
```

- **DNS A records** for the three public hosts pointing at the VPS IPv4 address (and AAAA for IPv6 if used):
  - `pad.example.com`
  - `auth.example.com`
  - `coder.example.com`

All three hosts must share a registrable parent domain (for example `.example.com`) because the gateway relies on a shared `session_id` cookie. Wildcard DNS for workspace subdomains is not required for the first deployment; path-based workspace apps are used.

## 4. Secrets and environment configuration

1. Copy the production template and restrict permissions:

   ```bash
   cp .env.prod.template .env
   chmod 600 .env
   ```

2. Generate secrets and fill every `__CHANGE_ME__` placeholder:

   ```bash
   # PostgreSQL owner (can be any username; use the same value everywhere .env expects it)
   openssl rand -hex 16

   # PostgreSQL password
   openssl rand -hex 32

   # Redis password
   openssl rand -hex 32

   # Keycloak admin password
   openssl rand -hex 32

   # OIDC client secret
   openssl rand -hex 32

   # Coder API key
   openssl rand -hex 32
   ```

3. Set the Docker group ID:

   ```bash
   getent group docker | cut -d: -f3
   ```

4. Set domains and derived URLs:

   ```dotenv
   PAD_DOMAIN=pad.example.com
   AUTH_DOMAIN=auth.example.com
   CODER_DOMAIN=coder.example.com
   COOKIE_DOMAIN=.example.com
   OIDC_SERVER_URL=https://auth.example.com
   REDIRECT_URI=https://pad.example.com/api/auth/callback
   FRONTEND_URL=https://pad.example.com
   CODER_URL=https://coder.example.com
   ```

5. Keep `OIDC_INTERNAL_URL` and `CODER_INTERNAL_URL` empty in production unless you need to override the internal Docker DNS names; the compose file defaults them to `http://keycloak:8080` and `http://coder:7080`.

`.env.prod.template` contains no working secrets. `scripts/startup.sh` refuses to start if any required secret or domain is empty or still a documented placeholder, and it never prints the value of the missing variable.

## 5. First start and startup order

Start the stack from the project root:

```bash
docker compose -f docker-compose.prod.yml up -d
```

The compose file defines the following startup order:

1. `postgres` and `redis` start first and must report healthy.
2. `pad`, `keycloak` and `coder` start after `postgres` (and `pad` also waits for `redis`).
3. `caddy` starts last after `pad`, `keycloak` and `coder` are healthy.

Verify health:

```bash
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs -f caddy
```

All services should reach the `healthy` state. If a service is stuck starting, check its logs first; the startup preflight in `pad` prints the name of any missing variable and exits non-zero.

## 6. Keycloak realm and client setup

Create or import a realm named `pad`. The local acceptance profile imports `deploy/keycloak/realm-export.json` automatically; production should match the same settings.

Realm settings:

| Setting | Value |
| --- | --- |
| Realm name | `pad` |
| Registration allowed | disabled |
| Email verification | required |
| Login with email | enabled |

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

**Exact redirect URIs** (no wildcards):

```text
https://pad.example.com/api/auth/callback
https://coder.example.com/api/v2/users/oidc/callback
```

**Exact web origins** (no wildcards):

```text
https://pad.example.com
https://coder.example.com
```

Add an **audience mapper** named `pad-audience` of type "Audience":

- Included Client Audience: `pad`
- Add to access token: `true`
- Add to ID token: `false`
- Add to userinfo: `false`

Create two realm roles:

| Role | Purpose |
| --- | --- |
| `pad-user` | Required to receive a Pad session (`PAD_ALLOWED_ROLES=pad-user`). |
| `admin` | Additional role used by Caddy to gate Keycloak `/admin*` paths. |

Assign `pad-user` to every user who should be able to log in. Assign both `pad-user` and `admin` to operators who need the Keycloak admin console.

See `deploy/keycloak/README.md` for the test realm export, the two-layer administrative model and break-glass access.

## 7. Coder setup and template bootstrap

> ⚠️ **Docker socket privilege**: `docker-compose.prod.yml` mounts `/var/run/docker.sock` into the Coder container. This is equivalent to granting host-level control to Coder and any workspace it creates. Run Coder only on a dedicated VPS with trusted users, keep the image patched, and restrict SSH access to the host. Rootless Docker or a socket proxy is follow-up work.

> ⚠️ **First user becomes owner**: the first Keycloak user to log into Coder becomes the Coder platform owner. Bootstrap with the intended operator account.

After the stack is healthy and the Keycloak realm is configured:

1. Open `https://coder.example.com` in a browser. You are redirected through Pad login to Keycloak.
2. Log in with the Keycloak user that should own Coder.
3. Create a provisioner API key at **Deployment → API keys** and add it to `.env` as `CODER_API_KEY`.
4. Copy the organization UUID from **Deployment → Organizations** into `CODER_DEFAULT_ORGANIZATION`.
5. Create or import a template at **Templates → Create template** and copy its UUID into `CODER_TEMPLATE_ID`.
6. Ensure `.env` contains:

   ```dotenv
   CODER_ACCESS_URL=https://coder.example.com
   CODER_OIDC_ISSUER_URL=https://auth.example.com/realms/pad
   CODER_OIDC_CLIENT_ID=pad
   CODER_OIDC_CLIENT_SECRET=<same OIDC_CLIENT_SECRET as Pad>
   CODER_OIDC_IGNORE_EMAIL_VERIFIED=false
   CODER_ADDITIONAL_CSP_POLICY=frame-ancestors https://pad.example.com
   ```

7. Recreate Coder and Pad to pick up the new values:

   ```bash
   docker compose -f docker-compose.prod.yml up -d --force-recreate coder pad
   ```

See `deploy/coder/README.md` for the full bootstrap procedure, the warning about the first owner and the reason automation is intentionally avoided.

## 8. Local `*.pad.test` acceptance mode

The local profile runs the same production topology on `*.pad.test` using Caddy's internal CA. No public DNS or ACME account is required.

1. Copy the local template:

   ```bash
   cp .env.local.template .env
   chmod 600 .env
   ```

2. Fill the generated secrets and the Docker group ID.
3. Add the hosts entries:

   ```text
   127.0.0.1 pad.pad.test auth.pad.test coder.pad.test
   ```

4. Start the stack:

   ```bash
   docker compose -f docker-compose.prod.yml up -d
   ```

5. Trust the Caddy root CA so HTTPS requests succeed without `-k`:

   ```bash
   docker cp caddy:/data/caddy/pki/authorities/local/root.crt /tmp/caddy-root.crt
   sudo cp /tmp/caddy-root.crt /usr/local/share/ca-certificates/caddy-local.crt
   sudo update-ca-certificates
   ```

   On macOS, import `/tmp/caddy-root.crt` into Keychain Access and trust it.

6. Verify the gateway:

   ```bash
   curl -i https://pad.pad.test
   ```

   An unauthenticated browser request should receive `302` to the Keycloak login page.

The test environment helper `scripts/test-env.sh` automates the local template generation and starts the stack together with `compose.test.yml`. Use it for acceptance suites:

```bash
scripts/test-env.sh up
```

## 9. Verification checklist

Run `scripts/smoke-test.sh` first; then exercise the user journeys below.

### Smoke test

```bash
# Anonymous checks only
PAD_BASE_URL=https://pad.pad.test \
  AUTH_BASE_URL=https://auth.pad.test \
  CODER_BASE_URL=https://coder.pad.test \
  CA_BUNDLE=/usr/local/share/ca-certificates/caddy-local.crt \
  ./scripts/smoke-test.sh

# With test credentials (optional)
PAD_BASE_URL=https://pad.pad.test \
  AUTH_BASE_URL=https://auth.pad.test \
  CODER_BASE_URL=https://coder.pad.test \
  CA_BUNDLE=/usr/local/share/ca-certificates/caddy-local.crt \
  OIDC_REALM=pad \
  PAD_TEST_USERNAME=user \
  PAD_TEST_PASSWORD='Password123!' \
  ./scripts/smoke-test.sh
```

### Manual checklist

| Check | Command / action | Expected result |
| --- | --- | --- |
| Anonymous Pad redirect | `curl -i https://pad.example.com/` | `302` to `/api/auth/login?rd=...` |
| API unauthorized | `curl -i -H 'Accept: application/json' https://pad.example.com/api/auth/verify` | `401` JSON, no HTML |
| Public static asset | `curl -i https://pad.example.com/favicon.ico` | Not `401`/`403`/`302` (a 404 is acceptable if the file is missing) |
| OIDC discovery | `curl -i https://auth.example.com/realms/pad/.well-known/openid-configuration` | `200` JSON with `"issuer"` |
| Admin deny (anonymous) | `curl -i https://auth.example.com/admin` | `302`, `401` or `403` |
| Security headers | `curl -I https://pad.example.com/` | `X-Content-Type-Options: nosniff`, `Referrer-Policy`, `Permissions-Policy`; in production also HSTS |
| Login | Open `https://pad.example.com` in a browser and log in | Redirect back to Pad with a `session_id` cookie |
| Pad CRUD | Create, rename and delete a pad | All operations succeed |
| WebSocket | Open a pad and add a drawing or terminal element | `wss://pad.example.com/ws/pad/{id}` connects and stays open |
| Coder terminal | Insert a terminal element | Coder iframe loads and the embedded terminal opens |
| Admin allow/deny | Access `https://auth.example.com/admin` as an admin from an allowed IP, then as a non-admin | Admin allowed; non-admin or wrong IP receives `403` |
| Logout | Click logout | `session_id` cookie cleared and Keycloak end-session URL reached |
| Replay | Replay the old `session_id` cookie against `https://pad.example.com/api/auth/verify` | `401` or `302` to login |
| Oversized request | `curl -d @11mb-file https://pad.example.com/api/pad/...` | `413 Payload Too Large` |

## 10. PostgreSQL backup/restore and Caddy certificate persistence

### Backup

`scripts/backup-postgres.sh` dumps the Pad, Keycloak and Coder databases to timestamped, compressed files. Run it from the project root with the production compose file active:

```bash
export COMPOSE_FILE=docker-compose.prod.yml
./scripts/backup-postgres.sh
```

The script creates `backups/` with mode `700` and files with mode `600`. It never prints passwords. To keep more than one backup, set a retention window:

```bash
BACKUP_RETENTION_DAYS=7 COMPOSE_FILE=docker-compose.prod.yml ./scripts/backup-postgres.sh
```

### Restore

Stop the stack, restore each database from its dump, then start again:

```bash
export COMPOSE_FILE=docker-compose.prod.yml
docker compose down

# Example restore for the pad database
gunzip < backups/pad_YYYYMMDD_HHMMSS.sql.gz | \
  docker compose exec -T postgres psql -U "$POSTGRES_USER" -d pad

# Repeat for keycloak and coder
gunzip < backups/keycloak_YYYYMMDD_HHMMSS.sql.gz | \
  docker compose exec -T postgres psql -U "$POSTGRES_USER" -d keycloak

gunzip < backups/coder_YYYYMMDD_HHMMSS.sql.gz | \
  docker compose exec -T postgres psql -U "$POSTGRES_USER" -d coder

docker compose up -d
```

Test restores into scratch databases periodically:

```bash
docker compose exec -T postgres psql -U "$POSTGRES_USER" -c 'CREATE DATABASE pad_restore;'
gunzip < backups/pad_YYYYMMDD_HHMMSS.sql.gz | \
  docker compose exec -T postgres psql -U "$POSTGRES_USER" -d pad_restore
```

### Caddy certificate persistence

Caddy stores certificates, the internal CA and configuration in the `caddy_data` and `caddy_config` volumes. They survive container recreation. In production the same data lets Caddy renew certificates; in local mode it preserves the internal CA root certificate so clients do not have to re-trust it after every recreation.

Back up `caddy_data` before recreating the Caddy container or migrating hosts:

```bash
mkdir -p ./backups
docker compose -f docker-compose.prod.yml run --rm --no-deps caddy \
  tar czf - -C /data . > ./backups/caddy_data_$(date +%Y%m%d_%H%M%S).tgz
```

## 11. Upgrade and rollback procedure

### Upgrade

1. Read `docker-compose.prod.yml` and note the image tags/digests currently running.
2. Back up PostgreSQL and Caddy data.
3. Pull new images or update the compose file.
4. Recreate services:

   ```bash
   docker compose -f docker-compose.prod.yml up -d --force-recreate
   ```

5. Run the smoke test and the manual checklist.
6. Watch Caddy certificate issuance and service health for at least 10 minutes.

### Rollback

If verification fails:

1. Stop the new stack:

   ```bash
   docker compose -f docker-compose.prod.yml down
   ```

2. Restore the previous `docker-compose.prod.yml` and `.env` from your version control or backup.
3. Restore the PostgreSQL dumps if the schema or data changed.
4. Restore the Caddy data volume if certificate state changed.
5. Start the previous stack:

   ```bash
   docker compose -f docker-compose.prod.yml up -d
   ```

Keep old volumes until the rollback is confirmed working.

## 12. Security considerations

### Shared-cookie blast radius

The gateway authenticates all three hosts with the same Pad session cookie. The cookie is scoped to the shared parent domain (`COOKIE_DOMAIN`) so that Caddy can validate it on `pad.example.com`, `coder.example.com` and `auth.example.com`. This means any host under that parent domain receives the cookie.

**Accepted risk**: a compromised sibling subdomain could read the shared cookie server-side.

Mitigations:

- Do not run untrusted services under the same parent domain.
- Keep `COOKIE_DOMAIN` as a registrable parent shared by exactly the three gateway hosts.
- Use short session TTLs tied to the Keycloak refresh lifetime.
- Revoke sessions immediately on logout (`session:*` deletion).
- Do not log cookie values.

### Cookie stripping and header isolation

Caddy strips the Pad `session_id` cookie before proxying to Coder and Keycloak:

```caddyfile
header_up Cookie "(^|;\\s*){$SESSION_COOKIE_NAME}=[^;]*(;\\s*)?" "$1"
```

Caddy also removes any client-supplied `X-Pad-User`, `X-Pad-Roles` and `X-Pad-Admin` headers before authentication and re-adds them only from the `forward_auth` response. Neither Coder nor Keycloak receives the Pad session cookie or spoofed identity headers.

### Docker socket host-level risk

Coder mounts the host Docker socket (`/var/run/docker.sock`). Any code running inside Coder or inside a Coder workspace can use that socket to create, modify or delete containers on the host, which is equivalent to host root access.

**Accepted risk**: workspace isolation is not a host security boundary in this deployment.

Mitigations:

- Use a dedicated VPS for this deployment.
- Allow only trusted users to log in.
- Restrict SSH and direct host access to operators.
- Keep Coder patched.
- Consider rootless Docker or a Docker socket proxy as follow-up work.

### Fail-closed `forward_auth`

Caddy delegates authentication to Pad's `/api/auth/verify`. If Pad is unavailable, returns an error or takes too long, Caddy denies the protected request with `502 Bad Gateway` or `503 Service Unavailable`. It never allows an unauthenticated request to reach Pad, Coder browser surfaces or Keycloak `/admin*`.

### Trusted-user policy

This deployment is designed for a small group of trusted users. Coder can run arbitrary containers with host-level privileges. Do not expose the gateway to the open internet or allow self-registration.

### Log redaction

Caddy access logs are filtered to remove:

- `Cookie` request header
- `Authorization` request header
- `code` and `state` query parameters

Pad application logs must not contain session identifiers, access tokens, refresh tokens, authorization codes or cookie values. Access logs live in the `caddy_data` volume on the host; protect them with host-level permissions.

### Residual risks

The accepted residual risks are tracked explicitly in the next section. In summary:

- A compromised sibling host can read the shared cookie.
- Coder's Docker socket access is equivalent to host root access.
- Secrets are visible in container environment variables to anyone with host access.
- Break-glass SSH access to Keycloak bypasses the Pad gate by design.

## 13. Residual risks and follow-up work

The following items are accepted for this change with a documented decision and follow-up reference.

| Item | Decision | Owner / follow-up reference |
| --- | --- | --- |
| Coder static-asset verification cost | Keep all Coder browser surfaces gated initially and measure latency. | Project: if latency is material, exempt `/static/*` and `/assets/*` or add a short-lived signed verification cache. |
| Image and dependency pinning | Workflow actions are pinned; container image digests and dependency lockfiles are follow-up. | Project: pin image digests in `docker-compose.prod.yml`, record digests for rollback, add `pip-audit`/`npm audit`/Trivy scanning. |
| Preflight across services | Pad validates its environment at startup; a compose-wide preflight is follow-up. | Project: add a preflight container or wrapper that validates every required value before any service starts. |
| Backup retention, offsite and encryption | Backups are local and unencrypted by default. | Operator: schedule backups, define retention, copy encrypted dumps off-site and run periodic restore drills. |
| Coder first-user ownership | Manual bootstrap gate. | Operator: log into Coder first with the intended owner account or assign owners explicitly; verify in staging. |
| Rate limiting | Out of scope for this change. | Project: document the risk or build a custom Caddy image with `rate_limit` later. |
| Monitoring and alerting | Healthchecks and logs only. | Project: add a monitoring stack (metrics/alerting) as a separate change. |
| Break-glass SSH to Keycloak | Accepted operator-only path. | Operator: restrict SSH to operators and document the tunnel in `deploy/keycloak/README.md`. |
| Coder workspace isolation | Out of scope; relies on Coder's own boundary. | Operator: accept that workspace isolation is not a host boundary; trusted users only. |
| Secrets in container environment | Accepted; `.env` is mode `0600` but values are visible to `docker inspect`. | Operator: restrict host access and consider an external secret manager as a follow-up. |

## 14. Troubleshooting

- **Certificate warnings in local mode**: re-run the CA trust command in section 8 and restart your browser.
- **`502 Bad Gateway` on protected paths**: check that `pad` is healthy and that `forward_auth` is not failing because of a missing `COOKIE_DOMAIN`.
- **Keycloak issuer errors**: ensure `KC_HOSTNAME` matches `OIDC_SERVER_URL` exactly.
- **Coder iframe refuses to load**: verify `CODER_ADDITIONAL_CSP_POLICY=frame-ancestors https://${PAD_DOMAIN}` and that the browser is using HTTPS.
- **Lost access to Keycloak admin**: use break-glass SSH tunnel access documented in `deploy/keycloak/README.md`.
