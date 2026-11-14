# Design

## Context

See `proposal.md` for motivation and the four delta specs for behavioral requirements.

The current repository runs every service with `network_mode: host` in `docker-compose.yml`: PostgreSQL on 5432, Redis on 6379, Keycloak on 8080, Coder on 7080 and Pad on 8000. Keycloak and Coder are configured with `localhost` URLs, Pad talks to them over `http://localhost`, and the browser reaches Coder through `CODER_URL`. Pad performs OIDC login in `auth_router.py`, stores token data in Redis under `session:{session_id}`, and validates sessions in `dependencies.py`. The frontend embeds Coder terminal pages in an iframe and silently primes the Coder OIDC session from `AuthGate.tsx`.

Constraints that shape the design:

- Single VPS, small trusted user group, Docker Compose only; no orchestrator.
- Coder requires the Docker socket and must remain able to provision workspace containers.
- Coder workspace apps are path-based in the current frontend (`/@{username}/{workspace}.{agent}/terminal`), so wildcard DNS is not required for the first deployment.
- Keycloak is both the Pad identity provider and the Coder identity provider; its OIDC endpoints must stay public.
- The stack must be testable without public DNS or ACME, because the operator may not own a domain yet.

## Goals / Non-Goals

**Goals:**

- One public entry point, TLS everywhere, no direct access to data stores or application ports.
- A single authentication decision at the edge, reusing the existing Pad/Keycloak session, with admin-only surfaces separated from user surfaces.
- A production compose stack that is reproducible, bounded in resources, observable through healthchecks/logs, and recoverable from PostgreSQL backup.
- A local acceptance mode that exercises the same routing and auth behavior with `*.pad.test` and an internal CA.
- Application changes limited to what the edge requires: CORS, cookies, OIDC state, redirect validation, proxy trust, public/internal URL split.

**Non-Goals:**

- Multi-tenant isolation inside Coder beyond what Coder itself provides.
- Hardening the Docker socket to a non-root API proxy; this design documents the risk and leaves privilege reduction as follow-up work.
- Per-workspace CPU/RAM/disk quotas.
- Wildcard `*.coder.example.com` workspace apps, DNS-01 and wildcard certificates.
- High availability, horizontal scaling, external secret managers, a full monitoring stack.
- Rewriting Pad's authentication away from Keycloak.

## Decisions

### D1. Caddy is the only public ingress

Caddy terminates TLS and routes by host:

```
Internet
   │ 80/443
   ▼
┌─────────┐
│  Caddy  │  pad.example.com   → pad:8000
│         │  auth.example.com  → keycloak:8080
│         │  coder.example.com → coder:7080
└────┬────┘
     │ private Docker network (no published ports)
     ├── pad ── postgres, redis, coder, keycloak
     ├── keycloak ── postgres
     ├── coder ── postgres, docker.sock
     ├── postgres
     └── redis
```

Only Caddy publishes `80:80`, `443:443` and `443:443/udp` (HTTP/3). Every other service uses `expose` only. The compose file has no `network_mode: host`; all services join a single user-defined bridge network so Docker DNS resolves `pad`, `postgres`, `redis`, `keycloak` and `coder`.

Alternatives considered:

- **Traefik**: comparable, but Caddy's `forward_auth`, automatic HTTPS and small Caddyfile are a better fit for a single-VPS deployment.
- **nginx**: requires manual certificate management or Certbot and more configuration for `auth_request`.
- **Keep host networking and bind to loopback**: lower migration risk for Coder, but does not satisfy the isolation requirement and leaves Docker's port publishing behavior easy to misconfigure. Rejected for the production stack; the development compose remains unchanged.

### D2. Edge authentication uses `forward_auth` to Pad

Caddy delegates the authentication decision to Pad because Pad already owns the Keycloak session and Redis store. The flow:

```
Browser → Caddy → GET /api/auth/verify (Pad)
                     │
        valid session ├─ 200 + X-Pad-User / X-Pad-Roles / X-Pad-Admin
                     │        → Caddy proxies original request
        browser, no  ├─ 302 → https://pad.../api/auth/login?rd=<original>
        API, no      └─ 401 JSON
```

Contract for `GET /api/auth/verify`:

| Case | Status | Response |
| --- | --- | --- |
| Valid session | `200` | `X-Pad-User: <uuid>`, `X-Pad-Roles: <comma list>`, `X-Pad-Admin: true|false`, `Cache-Control: no-store` |
| Expired access token, valid refresh token | `200` | Same headers after refresh |
| Browser navigation without session | `302` | `Location: <FRONTEND_URL>/api/auth/login?rd=<validated original URL>` |
| API/fetch without session | `401` | JSON `{"detail": "Not authenticated"}` |
| Verify endpoint unavailable | `5xx` | Caddy denies the protected request (fail closed) |

`rd` is built from `X-Original-Host` and `X-Original-URI`, which Caddy passes via `header_up`. Pad validates the host against the configured Pad/Coder/Keycloak hosts before redirecting.

Why not alternatives:

- **oauth2-proxy**: adds a second OIDC client and a second session. Pad would still validate its own session, so either the user logs in twice or Pad must trust proxy headers, which is a larger authentication rewrite. Rejected for this change.
- **Caddy basic auth on admin only**: simple, but does not satisfy "authenticate the entire Pad and Coder surfaces", has no SSO and no per-user identity.
- **Keycloak gatekeeper / Caddy Security plugin**: requires a custom Caddy build and duplicates identity logic. Standard `forward_auth` is sufficient.

Performance: `forward_auth` runs once per request, not per WebSocket message. Pad's verify path does a Redis lookup and a cached JWKS verification. Static assets are excluded from authentication, so page load cost is limited to API and navigation requests. If latency becomes measurable, the next step is a short-lived signed verification token cached by Caddy, not bypassing verification.

Fail-closed behavior is explicit: Caddy's `forward_auth` already denies on non-2xx, so a Pad outage returns `502/503` instead of allowing traffic.

### D3. Route protection matrix

| Host | Path | Auth | Notes |
| --- | --- | --- | --- |
| `PAD_DOMAIN` | `/api/auth/login`, `/api/auth/callback`, `/api/auth/status`, `/api/auth/logout` | Public | Login must work before a session exists; logout is idempotent. |
| `PAD_DOMAIN` | `/api/auth/verify` | Public | Called by Caddy; returns no secrets. |
| `PAD_DOMAIN` | `/assets/*`, `/static/*`, `/favicon.ico` | Public | Needed to render the post-login app and Coder popup close page. |
| `PAD_DOMAIN` | everything else, including `/`, `/pad/*`, `/api/pad/*`, `/api/users/*`, `/api/workspace/*`, `/ws/*` | `forward_auth` | Entire Pad host, including landing page, is gated. |
| `CODER_DOMAIN` | browser UI, OIDC callback, terminal and workspace WebSockets | `forward_auth` | Browser surfaces stay Pad-gated. |
| `CODER_DOMAIN` | `/api/v2/*` used by the CLI, workspace agents and IDE integrations | Coder token auth | Exempt from `forward_auth`; Coder validates its own session tokens. Exempt only the paths those clients actually use. |
| `AUTH_DOMAIN` | `/admin*` | `forward_auth` + `X-Pad-Admin: true` + optional IP allowlist | Keycloak admin console and admin REST. |
| `AUTH_DOMAIN` | `/realms/*`, `/resources/*` | Public | OIDC discovery, authorization, token, JWKS and login assets. |
| `AUTH_DOMAIN` | other paths | Public | Keycloak account pages rely on Keycloak's own session. |

The entire-Pad gate means the current anonymous landing page with `AuthDialog` is no longer the normal entry path: an unauthenticated browser is redirected to Keycloak before the SPA loads. `AuthDialog` remains as a fallback for session expiry inside an already-loaded SPA. This is a deliberate UX change consistent with the chosen scope.

The Coder gate applies to browser surfaces. The `coder` CLI, workspace agents and IDE integrations authenticate with Coder session tokens, not with the Pad cookie, so their API paths must bypass `forward_auth` and be authorized by Coder itself. Without this exception the terminal and `coder ssh` break even though the browser UI looks correct; the proxy suite must test a token-authenticated machine request, not only a browser.

Keycloak keeps its own public surface: OIDC endpoints and the account console authenticate against Keycloak directly. Account registration is disabled, and only provisioned users receive a Pad session, otherwise a self-registered Keycloak user would pass the Pad gate and reach Coder.

### D4. Shared session cookie and header isolation

Pad sets the session cookie as:

```
session_id=<opaque random>; Domain=.example.com; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age=<refresh lifetime>
```

`Domain` comes from `COOKIE_DOMAIN`; in local mode it is `.pad.test`; when unset (pure host-only development) the attribute is omitted. `SameSite=Lax` is compatible with the Keycloak top-level redirect back to Pad and with Coder iframes because `pad.example.com` and `coder.example.com` are same-site (same registrable domain).

Because the cookie is sent to sibling hosts, Caddy strips it before proxying to Coder and Keycloak:

```caddyfile
header_up Cookie "(^|;\\s*)session_id=[^;]*(;\\s*)?" "$1"
```

This is a regular expression replacement supported by `reverse_proxy`'s `header_up`. Coder and Keycloak administrative paths therefore never receive Pad's session cookie, while Caddy can still validate it. Pad's own upstream keeps the cookie because the backend needs it. The same strip must be applied to the public Keycloak blocks; otherwise the account console and OIDC endpoints receive a cookie they do not need.

If `SESSION_COOKIE_NAME` is configurable, the Caddy validation and stripping expressions must use the same value; the default remains `session_id`. `COOKIE_DOMAIN` must be a registrable parent domain shared by the three hosts, not a public suffix, and startup validates it.

Client-supplied identity headers are removed at the start of every protected site block:

```caddyfile
request_header -X-Pad-User
request_header -X-Pad-Roles
request_header -X-Pad-Admin
```

Only `forward_auth`'s `copy_headers` may add them back, and the reverse proxy strips them again before Coder/Keycloak. Pad does not treat these headers as authentication; it validates the cookie itself.

Residual risk: a compromised sibling host can read the shared cookie server-side. Mitigations are cookie stripping, no untrusted subdomains under the parent domain, short session TTL, immediate Redis revocation and access logs that never record cookie values.

### D5. OIDC state, session fixation and logout

Current code uses `state=default` or `state=popup` and does not validate it. The design replaces it with a server-side login transaction:

1. `GET /api/auth/login?rd=...` validates `rd`, generates `state` (32 random bytes) and a login transaction ID.
2. Pad stores `oidc_state:{state}` in Redis with `{mode, rd, created_at}` and a 10-minute TTL.
3. Pad sets an `oidc_state` cookie with the same random value (`HttpOnly`, `Secure`, `SameSite=Lax`, `Path=/api/auth`, `Max-Age=600`) and redirects to Keycloak with `state`.
4. `GET /api/auth/callback?code=...&state=...` requires the query `state` to match both the cookie and the Redis record.
5. Pad deletes the Redis record and the state cookie, verifies that the user is provisioned for Pad access, generates a **new** `session_id`, stores tokens under `session:{new_id}`, and sets the session cookie. An authenticated but unprovisioned user receives `403` and no session.
6. Pad redirects to the validated `rd`, or `/`.

The separate state cookie prevents login CSRF where an attacker supplies a valid state/code pair from their own browser. Rotating the session ID at callback prevents session fixation. The popup mode is carried in the Redis transaction, not in the `state` value, so `state` stays opaque.

Logout deletes `session:{id}`, clears the cookie with the same `Domain`/`Path`, ends the Coder session for the same browser and returns the Keycloak end-session URL. Clearing only the Pad session is not enough: Coder keeps its own host cookie, so a second Pad user on the same browser would inherit the first user's Coder session. The implementation therefore calls Coder's logout endpoint or clears its session cookie before redirecting, and the E2E suite covers the user-switch case.

Token refresh is single-flight. `verify` may refresh on demand, and the existing `/api/auth/refresh` endpoint remains for the SPA; both paths must share a per-session lock or refresh coordinator so they never rotate the same refresh token concurrently. Session lifetimes are explicit: the access token, refresh token and cookie `Max-Age` are documented values, and a cookie that expires before the server-side session relies on silent re-authentication through the Keycloak SSO session, which is tested.

### D6. Public and internal service URLs

One URL cannot serve both the browser and the backend safely:

- The browser must use `https://auth.example.com` and `https://coder.example.com`.
- Pad's backend should use `http://keycloak:8080` and `http://coder:7080` to avoid hairpin traffic through Caddy and to keep working if the public path is degraded.
- Keycloak tokens will carry `iss=https://auth.example.com` even when fetched internally, so Pad must validate the issuer explicitly.

The design splits configuration:

| Variable | Consumer | Example |
| --- | --- | --- |
| `OIDC_SERVER_URL` | Browser authorization URL, issuer validation | `https://auth.example.com` |
| `OIDC_INTERNAL_URL` | Token exchange and JWKS fetch | `http://keycloak:8080` |
| `CODER_URL` | Frontend config, iframe base URL, workspace `base_url` | `https://coder.example.com` |
| `CODER_INTERNAL_URL` | Pad backend Coder API calls | `http://coder:7080` |

`OIDC_INTERNAL_URL` defaults to `OIDC_SERVER_URL` and `CODER_INTERNAL_URL` defaults to `CODER_URL` for development compatibility. JWT validation adds `issuer=OIDC_SERVER_URL + "/realms/" + OIDC_REALM`; audience validation remains `OIDC_CLIENT_ID`. This catches tokens minted for another realm or issuer.

`workspace_router.py` must return `base_url = CODER_URL`; `app_router.py` must return `coderUrl = CODER_URL`; `coder.py` must use `CODER_INTERNAL_URL`. This is a small but critical change: using the internal URL in the frontend would make the terminal iframe resolve `coder:7080` in the browser, which fails.

### D7. Production compose topology and operations

`docker-compose.prod.yml` contains:

| Service | Image | Ports | Persistent | Limits (initial) | Health |
| --- | --- | --- | --- | --- | --- |
| `caddy` | `caddy:2-alpine` | `80`, `443` | `caddy_data`, `caddy_config` | 0.5 CPU / 256 MB | `caddy version` |
| `pad` | `ghcr.io/pad-ws/pad.ws:main` | expose 8000 | none | 1 CPU / 512 MB | `GET /` |
| `postgres` | `postgres:16` | expose 5432 | `postgres_data` | 1 CPU / 1 GB | `pg_isready` |
| `redis` | `redis:alpine` | expose 6379 | `redis_data` | 0.5 CPU / 256 MB | `redis-cli ping` |
| `keycloak` | `quay.io/keycloak/keycloak:25.0` | expose 8080 | PostgreSQL | 1 CPU / 1 GB | health endpoint if available |
| `coder` | `ghcr.io/coder/coder:latest` | expose 7080 | PostgreSQL | 1 CPU / 1 GB | `/healthz` |

Each service gets its own PostgreSQL database on the shared instance: `pad`, `keycloak` and `coder`. Pad keeps its `pad_ws` schema; Keycloak and Coder must not share the `public` schema or a migration history. An init script creates the three databases before services start, and the backup script dumps all three.

Operational defaults:

- `restart: unless-stopped` for all services.
- `depends_on` with `condition: service_healthy` for PostgreSQL and Redis dependencies.
- `logging.options.max-size: 10m`, `max-file: 3` for every service.
- `mem_limit`, `cpus`, `pids_limit` rather than Swarm-only `deploy.resources` so plain `docker compose` enforces them.
- `security_opt: no-new-privileges:true` for services that do not require extra privileges; Coder is excluded because it manages Docker.
- PostgreSQL `shm_size: 256mb`.
- Coder mounts `/var/run/docker.sock` and `group_add: ${DOCKER_GROUP_ID}`. The runbook states that this is host-level control and that Coder is only for trusted users.

Keycloak environment:

```dotenv
KC_HOSTNAME=https://auth.example.com
KC_HOSTNAME_STRICT=true
KC_HOSTNAME_STRICT_HTTPS=true
KC_HTTP_ENABLED=true
KC_PROXY_HEADERS=xforwarded
KC_DB=postgres
KC_DB_URL=jdbc:postgresql://postgres:5432/${KEYCLOAK_DB}
KC_DB_USERNAME=${POSTGRES_USER}
KC_DB_PASSWORD=${POSTGRES_PASSWORD}
KC_HEALTH_ENABLED=true
```

`KC_PROXY_HEADERS=xforwarded` trusts Caddy's `X-Forwarded-*`; Keycloak is not published, so only Caddy can supply them. `KC_HOSTNAME` must match `OIDC_PUBLIC_URL` or issuer validation fails.

Coder environment:

```dotenv
CODER_ACCESS_URL=https://coder.example.com
CODER_HTTP_ADDRESS=0.0.0.0:7080
CODER_OIDC_ISSUER_URL=https://auth.example.com/realms/${OIDC_REALM}
CODER_OIDC_CLIENT_ID=${OIDC_CLIENT_ID}
CODER_OIDC_CLIENT_SECRET=${OIDC_CLIENT_SECRET}
CODER_OIDC_IGNORE_EMAIL_VERIFIED=false
CODER_ADDITIONAL_CSP_POLICY=frame-ancestors https://pad.example.com
CODER_PG_CONNECTION_URL=postgresql://${POSTGRES_USER}:${CODER_DB_PASSWORD_URLENCODED}@postgres:5432/${CODER_DB}?sslmode=disable
CODER_OAUTH2_GITHUB_DEFAULT_PROVIDER_ENABLED=false
```

`CODER_WILDCARD_ACCESS_URL` is left unset for path-based workspace apps. If a template requires subdomain apps, that is a follow-up change with wildcard DNS and DNS-01.

Secrets and configuration live in `.env` (mode `0600`) loaded via `env_file`. `.env.prod.template` contains placeholders only. The stack must fail fast when `POSTGRES_PASSWORD`, `REDIS_PASSWORD`, `KEYCLOAK_ADMIN_PASSWORD`, `OIDC_CLIENT_SECRET`, `CODER_API_KEY` or domain variables are empty. Startup scripts validate required variables and print the missing names; they never print values.

Backup: a `scripts/backup-postgres.sh` runs `pg_dump` inside the PostgreSQL container and writes a timestamped compressed dump to a host directory with restrictive permissions. The runbook documents restore into a fresh volume and a test restore into a scratch database. Caddy's `caddy_data` volume holds certificates and the local CA; it is backed up separately or allowed to re-issue certificates.

### D8. Caddyfile structure

Production and local mode share the same site blocks; only the TLS policy and domain values differ. Keep two files to avoid conditional Caddyfile logic:

- `deploy/Caddyfile` — production, automatic HTTPS with `{$ACME_EMAIL}`.
- `deploy/Caddyfile.local` — `tls internal` for `*.pad.test`.

Shared snippets:

```caddyfile
(security_headers) {
    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains"
        X-Content-Type-Options "nosniff"
        Referrer-Policy "strict-origin-when-cross-origin"
        Permissions-Policy "camera=(), microphone=(), geolocation=()"
        -Server
    }
}

(pad_auth) {
    forward_auth pad:8000 {
        uri /api/auth/verify
        header_up X-Original-Host {host}
        header_up X-Original-URI {uri}
        copy_headers X-Pad-User X-Pad-Roles X-Pad-Admin
    }
}
```

Pad site, simplified:

```caddyfile
{$PAD_DOMAIN} {
    import security_headers
    header X-Frame-Options "SAMEORIGIN"
    encode zstd gzip
    request_body { max_size 10MB }

    @pad_public path /api/auth/login* /api/auth/callback* /api/auth/status /api/auth/logout /api/auth/verify /assets/* /static/* /favicon.ico
    handle @pad_public {
        reverse_proxy pad:8000
    }

    handle {
        request_header -X-Pad-User
        request_header -X-Pad-Roles
        request_header -X-Pad-Admin
        import pad_auth
        reverse_proxy pad:8000
    }
}
```

Coder site, simplified:

```caddyfile
{$CODER_DOMAIN} {
    import security_headers
    encode zstd gzip

    # CLI, workspace agents and IDE integrations authenticate with Coder tokens.
    @coder_api path /api/v2/*
    handle @coder_api {
        reverse_proxy coder:7080 {
            header_up Cookie "(^|;\\s*)session_id=[^;]*(;\\s*)?" "$1"
            header_up -X-Pad-User
            header_up -X-Pad-Roles
            header_up -X-Pad-Admin
        }
    }

    handle {
        request_header -X-Pad-User
        request_header -X-Pad-Roles
        request_header -X-Pad-Admin
        import pad_auth
        reverse_proxy coder:7080 {
            header_up Cookie "(^|;\\s*)session_id=[^;]*(;\\s*)?" "$1"
            header_up -X-Pad-User
            header_up -X-Pad-Roles
            header_up -X-Pad-Admin
        }
    }
}
```

Keycloak site, simplified:

```caddyfile
{$AUTH_DOMAIN} {
    import security_headers
    encode zstd gzip

    @keycloak_public path /realms/* /resources/* /robots.txt
    handle @keycloak_public {
        reverse_proxy keycloak:8080 {
            header_up Cookie "(^|;\\s*)session_id=[^;]*(;\\s*)?" "$1"
        }
    }

    @admin_path path /admin*
    handle @admin_path {
        request_header -X-Pad-User
        request_header -X-Pad-Roles
        request_header -X-Pad-Admin
        import pad_auth
        @admin_allowed {
            header X-Pad-Admin true
            remote_ip {$ADMIN_ALLOWLIST}
        }
        @not_admin not {
            header X-Pad-Admin true
            remote_ip {$ADMIN_ALLOWLIST}
        }
        respond @not_admin 403
        reverse_proxy @admin_allowed keycloak:8080 {
            header_up Cookie "(^|;\\s*)session_id=[^;]*(;\\s*)?" "$1"
            header_up -X-Pad-User
            header_up -X-Pad-Roles
            header_up -X-Pad-Admin
        }
    }

    handle {
        reverse_proxy keycloak:8080 {
            header_up Cookie "(^|;\\s*)session_id=[^;]*(;\\s*)?" "$1"
        }
    }
}
```

`ADMIN_ALLOWLIST` defaults to `0.0.0.0/0 ::/0` (space-separated) in local mode and must be set to the operator's IPv4 and IPv6 CIDRs in production. Comma-separated values are not valid for Caddy's `remote_ip` matcher, and startup validates the format. If the operator leaves it open, the admin role is still required; the allowlist is defense in depth.

The `header_up Cookie` regex must be validated against a real browser cookie header; cookies with multiple values and whitespace are the edge case. `header_up -X-Pad-*` uses suffix wildcard deletion supported by Caddy.

Access logs:

```caddyfile
log {
    output file /data/access.log {
        roll_size 10MiB
        roll_keep 5
    }
    format filter {
        wrap json
        fields {
            request>headers>Cookie delete
            request>headers>Authorization delete
            request>uri query {
                delete code
                delete state
            }
        }
    }
}
```

Caddy logs all request headers by default, and the URI includes the query string, so `Cookie`, `Authorization`, `code` and `state` would appear unless filtered. The configuration must use an explicit `format filter` and a test must prove the values are absent. The local profile omits HSTS so the internal CA does not get pinned in the browser.

### D9. Application changes

| Area | Change |
| --- | --- |
| `config.py` | Add `PAD_DOMAIN`, `AUTH_DOMAIN`, `CODER_DOMAIN`, `COOKIE_DOMAIN`, `OIDC_INTERNAL_URL`, `CODER_INTERNAL_URL`, `ADMIN_ALLOWLIST`, `SESSION_COOKIE_NAME`, `TRUSTED_PROXY_IPS`. Keep `OIDC_SERVER_URL` and `CODER_URL` as the public values, default the internal URLs to them for development, and make `get_jwks_client()` use `OIDC_INTERNAL_URL`. |
| `domain/session.py` | Use `OIDC_SERVER_URL` for `get_auth_url`, `OIDC_INTERNAL_URL` for token/JWKS; add issuer validation; keep the existing Redis key layout. |
| `dependencies.py` | Validate issuer; expose a helper that returns the session or a structured auth failure for the verify endpoint. |
| `auth_router.py` | Add `/api/auth/verify`; replace fixed `state` with random state + Redis transaction + state cookie; add `rd` validation; rotate session ID at callback; set domain/cookie flags consistently; make logout idempotent and clear the shared cookie. |
| `main.py` | Replace wildcard credentialed CORS with `FRONTEND_URL` (and `DEV_FRONTEND_URL` only in dev mode); keep the rest of the route surface unchanged. |
| `coder.py` | Use `CODER_INTERNAL_URL` for API calls. |
| `workspace_router.py` | Return `CODER_URL` as `base_url`. |
| `app_router.py` | Return `CODER_URL` as `coderUrl`. |
| `scripts/startup.sh` | Run Uvicorn with `--proxy-headers --forwarded-allow-ips=${TRUSTED_PROXY_IPS}`; validate required environment variables before starting. |
| Frontend | No functional rewrite required. `AuthGate` still primes Coder after Pad login. Logout continues to use `/api/auth/logout`. The anonymous landing page becomes unreachable through Caddy by design; `AuthDialog` remains a fallback. |

`TRUSTED_PROXY_IPS` is `*` in the compose stack because Pad is not published and only Caddy can reach it. Caddy overwrites `X-Forwarded-For`/`X-Forwarded-Proto` on the proxy hop, so a client cannot smuggle a trusted scheme. A stricter future option is a dedicated proxy network with a fixed Caddy IP and that IP in `TRUSTED_PROXY_IPS`.

### D10. Test architecture and acceptance gates

Tests are part of the change, not a post-implementation activity. Suites live under `tests/` and are organized by the layer they exercise:

| Directory | Tooling | Scope | Gate |
| --- | --- | --- | --- |
| `tests/unit` | pytest, fakeredis, monkeypatch | state, `rd`, cookies, CORS, roles, issuer, config guards | CI, blocking |
| `tests/integration` | pytest, httpx, compose services | Pad + PostgreSQL + Redis + Keycloak | CI, blocking |
| `tests/proxy` | pytest/httpx + curl | Caddy route matrix, headers, limits, timeouts | CI, blocking |
| `tests/e2e` | Playwright | login, Pad, WebSocket, Coder, logout | CI when a template exists, otherwise staging |
| `tests/security` | pytest/httpx | CORS, CSRF, redirect, fixation, replay, spoofing, ports | CI, blocking |
| `tests/deploy` | bash + compose | invariants, backup/restore, recreation, port scan | CI for invariants and backup, staging for scan |

Decisions:

- **Test through Caddy.** Proxy, E2E and security suites address `https://*.pad.test`, never `pad:8000` or `coder:7080`. Only negative port-access tests target internal ports, and they assert refusal. This is the only way to catch a proxy that authenticates incorrectly while the application itself works.
- **Real dependencies for security-critical paths.** State, session, refresh and revocation tests use real Redis and Keycloak rather than mocks. Mocks are limited to unit tests of pure validation logic.
- **Reproducible environment.** `compose.test.yml` builds Pad from the working tree and imports a committed Keycloak realm export with admin/non-admin users and exact redirect URIs. A `make test-env` target brings it up on `*.pad.test` with the internal CA, so CI needs no public DNS.
- **Coder is the expensive dependency.** Coder needs the Docker socket and a provisioned template. The E2E suite automates the embedded terminal when the template exists; otherwise the check is a blocking staging gate with recorded evidence, never a silent skip.
- **Authorization and machine clients are first-class tests.** The suite includes an unprovisioned Keycloak user, a user switch on one browser, and a token-authenticated Coder CLI/agent request. Browser-only tests would miss both failure modes: a self-registered user passing the gate and the CLI/agents being blocked by it.
- **Commit and workflow hygiene is enforced in CI.** Commit messages and PR titles follow Conventional Commits, `actionlint` validates workflows, and every `uses:` is pinned to a 40-character commit SHA with a release comment. `scripts/check-actions-pinned.sh` fails the build on a floating tag, so a workflow cannot silently execute an unreviewed action version.
- **Traceability over test count.** `docs/testing.md` maps every scenario in the four behavioral specs to a test or gate with a stable criterion ID. A blocking scenario without a mapped check fails verification. The matrix is the review artifact; raw pass counts are not.
- **Testability refactor is in scope.** `config.py` reads the environment at import, `dependencies.py` keeps a module-level `oidc_config`, and `get_jwks_client()` caches globally. The change moves these behind a small factory or fixture seam so unit tests do not depend on import order or ambient environment.
- **CI and manual gates are separate.** Blocking automated suites run on every change to auth, Caddy, compose or deployment scripts. ACME issuance, a clean Debian/Ubuntu install, an external port scan and a real Coder workspace are documented manual gates; release requires both.

Alternatives considered:

- **Only a smoke script**: cheap, but it cannot prove negative cases (spoofing, replay, CSRF) and gives no per-scenario evidence. Rejected.
- **Mock Keycloak and Redis everywhere**: fast, but it would not catch issuer/audience mistakes or session revocation regressions. Kept only for pure logic.
- **Test Pad directly and assume Caddy works**: misses the exact failure this change introduces — a correct application behind a misconfigured proxy. Rejected.

### D11. Residual risks and follow-up

The following items are accepted for this change with documented residual risk or deferred to a follow-up change:

| Item | Decision | Mitigation / follow-up |
| --- | --- | --- |
| Coder static assets behind `forward_auth` | Keep gated initially | Measure latency; exempt `/static/*` and `/assets/*` or cache verification if it is material |
| Image and dependency pinning | Workflow actions are pinned now; container images and lockfiles remain follow-up | Actions use full commit SHAs; still pin image digests and dependency lockfiles, add `pip-audit`/`npm audit`/Trivy, record digests for rollback |
| Preflight across services | Follow-up | Add a compose preflight that validates every required value before any service starts, not only inside Pad |
| Backup retention, offsite and encryption | Runbook follow-up | Schedule, retention, off-site copy, encrypted dumps and a periodic restore drill |
| Coder first user becomes owner | Runbook gate | Bootstrap the admin first or assign the owner explicitly; verify in staging |
| Rate limiting | Out of scope | The standard `caddy:2-alpine` build has no `rate_limit`; document the risk or add a custom build later |
| Monitoring and alerting | Out of scope | Healthchecks and logs only; a monitoring stack is a follow-up change |
| Break-glass SSH to Keycloak | Accepted | Operator-only path that bypasses the Pad gate by design; documented in the runbook |
| Coder workspace isolation | Out of scope | Coder's own boundary; trusted users only |
| Secrets in container environment | Accepted | `.env` mode `0600`, but values are visible to `docker inspect`; document and restrict host access |

## Risks / Trade-offs

- **Shared cookie widens the blast radius of a compromised sibling host** → strip `session_id` before Coder/Keycloak, keep no untrusted subdomains, short session TTL, immediate Redis revocation, no cookie values in logs.
- **Caddy plus Pad is a single point of failure for the whole deployment** → restart policies, healthchecks, fail-closed `forward_auth`, documented break-glass access to Keycloak via SSH tunnel, and a rollback path.
- **Coder on a bridge network may not match the current workspace template assumptions** → validate the existing template in staging before cutover. If the template requires host networking, treat it as an explicit documented exception with a follow-up spec change rather than silently reverting the whole topology.
- **Docker socket grants host-level control** → dedicated VPS, trusted users only, no public Coder admin access beyond Caddy, Coder patched, runbook warning. Rootless Docker or a socket proxy is follow-up work.
- **Keycloak admin depends on Pad being available** → keep a documented SSH tunnel to the internal Keycloak port as break-glass access; the allowlist and admin role are additive, not the only recovery path.
- **Third-party cookie restrictions can break the Coder iframe** → use sibling subdomains (same-site), test Safari/Firefox private mode, keep path-based workspace apps on the same Coder host, and document fallback to opening Coder in a top-level tab.
- **Per-request `forward_auth` adds latency** → exclude static assets, keep verify cheap (Redis + cached JWKS), measure before considering a short-lived signed cache token.
- **CORS tightening can break local frontend development** → allow `DEV_FRONTEND_URL` only when `PAD_DEV_MODE=true`; production uses exactly `FRONTEND_URL`.
- **Logout does not revoke Coder's own session** → Caddy blocks all Coder access after Pad logout; direct Coder access is impossible. A future task can call Coder logout for defense in depth.
- **ACME rate limits or DNS mistakes can block first deployment** → local `tls internal` acceptance first, then production DNS with a dry run; Caddy retries certificates and logs the failure.

## Migration Plan

1. **Back up** the existing PostgreSQL database (`pg_dump`), `.env`, Keycloak realm export and Coder configuration. Record the current image digests.
2. **Prepare DNS**: `PAD_DOMAIN`, `AUTH_DOMAIN`, `CODER_DOMAIN` A records to the VPS; optionally `*.coder.example.com` only if subdomain apps are in scope later.
3. **Prepare the host**: Docker Engine/Compose, firewall allowing only SSH and 80/443, a non-root deployment user, `.env` with mode `0600`, generated secrets.
4. **Configure Keycloak**: realm, confidential client, exact redirect URIs, exact web origins, admin user, audience mapper. Remove wildcard redirects.
5. **Local acceptance**: start the production compose with `Caddyfile.local`, `*.pad.test` and `CADDY_TLS=internal`; trust the Caddy root CA; run the smoke checklist (login, Pad CRUD, WebSocket, Coder terminal, admin allowed/denied, logout, replay, oversized request).
6. **Production cutover**: stop the old stack, start the new stack with `Caddyfile`, verify certificates and OIDC issuer. Restore the database dump if the new PostgreSQL volume is fresh.
7. **Verify**: `docker compose ps` health, Caddy certificate chain, login through Keycloak, Pad access, Coder terminal, Keycloak admin from allowed/denied addresses, 401/403/302 behavior, access logs without secrets.
8. **Rollback**: stop the new stack, restore the previous compose and `.env`, restore the database dump if the schema or data changed, restart the old stack. Keep the old volumes until verification completes.

## Open Questions

None that change the specs, approach or task breakdown. The only unresolved implementation detail is whether the current Coder template needs host networking or subdomain apps; it is handled as a staging validation with an explicit fallback and follow-up change.