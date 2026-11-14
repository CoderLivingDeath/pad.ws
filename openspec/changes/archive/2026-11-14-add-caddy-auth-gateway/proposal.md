# Proposal

## Why

The current self-hosting setup is not safe to expose on a VPS: every service uses host networking and binds to public interfaces, Pad, Keycloak and Coder are served over plain HTTP, default credentials remain in `.env.template`, CORS allows every origin with credentials, and OIDC redirect URIs are configured with wildcards. The project needs a single hardened entry point so that only HTTPS reaches the internet and every application surface is authenticated before it is proxied.

## What Changes

- Add **Caddy** as the only public ingress. It terminates TLS (Let's Encrypt in production, an internal CA for local tests), routes `pad`, `auth` and `coder` hosts, proxies WebSockets, applies security headers and request limits, and forwards access logs.
- Add a **Caddy auth layer** based on `forward_auth` to a new Pad endpoint `GET /api/auth/verify`. The endpoint validates the existing Redis/OIDC session, refreshes it when needed, and returns the user identity and roles. Unauthenticated browser requests are redirected to Keycloak; API requests receive `401`.
- Protect the **entire Pad host, including the landing page**, plus Coder browser surfaces and Keycloak admin paths. Coder's token-authenticated `/api/v2/*` machine API remains reachable for the CLI, workspace agents and IDE integrations. Keycloak OIDC endpoints (`/realms/*`, `/resources/*`) and the account console remain public because login depends on them. Keycloak `/admin*` additionally requires the `admin` role and an optional IP allowlist.
- Introduce a **production compose stack** (`docker-compose.prod.yml`) with a private bridge network, no `network_mode: host`, no published ports for PostgreSQL, Redis, Keycloak, Coder or Pad, healthchecks, restart policies, resource limits, log rotation and named volumes. Only Caddy publishes `80/443`.
- Make **domains and TLS optional/configurable** (`PAD_DOMAIN`, `AUTH_DOMAIN`, `CODER_DOMAIN`, `COOKIE_DOMAIN`, `CADDYFILE=deploy/Caddyfile|deploy/Caddyfile.local`). Provide a local acceptance mode using `*.pad.test` and Caddy's internal CA, so the stack can be tested without public DNS or certificates.
- Replace insecure defaults with a `.env.prod.template` that contains no working passwords or secrets, documents required values, and separates production from local test configuration.
- Apply the **minimum application hardening required by the new edge**: origin-restricted CORS, secure session cookies with a shared parent domain, OIDC `state` validation, safe post-login redirects, trusted proxy headers for Uvicorn, exact Keycloak redirect URIs, Coder `frame-ancestors` restricted to the Pad origin, and `CODER_OIDC_IGNORE_EMAIL_VERIFIED=false`.
- Keep **Coder machine clients working**: the CLI, workspace agents and IDE integrations authenticate with Coder tokens on `/api/v2/*`, while the browser UI remains Pad-gated. Pad sessions are issued only to provisioned Keycloak users, self-registration is disabled, and logout ends the Coder session for the same browser.
- Make **session behavior explicit**: single-flight token refresh, documented access/refresh/cookie lifetimes, and WebSocket handshake plus periodic session revalidation.
- Run **separate PostgreSQL databases** for Pad, Keycloak and Coder, and **redact** cookies, authorization headers and OIDC query parameters from access logs.
- Add a **deployment runbook** covering DNS, secrets, first start, verification, backup/restore and rollback.
- Add an **acceptance test capability**: automated unit, integration, proxy, browser E2E, security and deployment suites that run through Caddy, a reproducible local test environment, a traceability matrix and documented manual staging gates.

**BREAKING**: services are no longer reachable through host ports; existing deployments must migrate to the new compose file and set `PAD_DOMAIN`, `AUTH_DOMAIN`, `CODER_DOMAIN`, `COOKIE_DOMAIN`, `OIDC_SERVER_URL`, `REDIRECT_URI` and `FRONTEND_URL` to their public HTTPS values. Keycloak client redirect URIs must be exact; wildcard entries must be removed. Keycloak self-registration is disabled and users must be provisioned. Coder CLI and workspace agents rely on `/api/v2/*` remaining outside `forward_auth`. Each service gets its own PostgreSQL database.

## Capabilities

### New Capabilities

- `edge-gateway`: Caddy is the sole public ingress, terminates TLS, routes hosts, proxies WebSockets, applies security headers and request limits, and emits access logs.
- `edge-authentication`: every protected host/path is authenticated through Caddy `forward_auth` and the Pad session; OIDC login endpoints stay reachable; admin surfaces require the `admin` role and optional IP allowlist.
- `production-deployment`: the production compose topology isolates services on a private network, removes insecure defaults, defines healthchecks, limits, volumes, backups and a domain-optional local test mode.
- `application-security`: Pad's browser-facing security defaults (CORS, cookies, OIDC state, redirect validation, proxy trust) are safe under a reverse proxy.
- `acceptance-testing`: the deployment is verifiable end to end through Caddy, with automated suites, a reproducible test environment, per-scenario traceability and explicit manual staging gates.

### Modified Capabilities

None. The project has no existing specs.

## Impact

- **Infrastructure**: new `docker-compose.prod.yml`, `Caddyfile`, `.env.prod.template`, local test env/Caddy profile, backup script for all service databases, PostgreSQL init script for separate databases, test compose profile, committed Keycloak realm export, `tests/` suites, `docs/testing.md`, `docs/ci.md` and CI test/lint jobs (commitlint, actionlint, SHA-pinned actions); existing `docker-compose.yml` remains the development stack.
- **Backend**: `src/backend/main.py` (CORS and CSRF origin checks), `src/backend/routers/auth_router.py` (state, cookies, safe redirect, verify endpoint, authorization predicate, single-flight refresh, Coder logout), `src/backend/routers/ws_router.py` (Origin and session revalidation), `src/backend/dependencies.py` (reusable session verification), `src/backend/config.py` (domain/cookie/proxy settings and a testable settings seam), `scripts/startup.sh` (proxy headers, required-variable checks).
- **Frontend**: logout/redirect handling and any login-link behavior that assumes a public landing page.
- **External configuration**: Keycloak realm/client redirect URIs, exact web origins, disabled self-registration and the separate Pad/Keycloak admin role mappings; Coder `CODER_ACCESS_URL`, the `/api/v2/*` machine-client exception, `CODER_ADDITIONAL_CSP_POLICY`, OIDC issuer, and DNS records for the three hosts.
- **Out of scope**: full multi-tenant workspace isolation, Docker socket privilege reduction beyond documentation, per-workspace CPU/RAM quotas, a monitoring stack, wildcard `*.coder.example.com` apps and high availability. These are recorded as follow-up work.