# Tasks

## 1. Configuration and environment

- [x] 1.1 Add the new settings to `src/backend/config.py`: `PAD_DOMAIN`, `AUTH_DOMAIN`, `CODER_DOMAIN`, `COOKIE_DOMAIN`, `OIDC_INTERNAL_URL`, `CODER_INTERNAL_URL`, `ADMIN_ALLOWLIST`, `SESSION_COOKIE_NAME`, `TRUSTED_PROXY_IPS`. Verify a development import succeeds and internal URLs fall back to `OIDC_SERVER_URL` and `CODER_URL` when unset.
- [x] 1.2 Add `.env.prod.template` with placeholders only and update `.env.template` comments to distinguish development from production. Verify `grep -E 'admin123|redis123|your_.*_key' .env.prod.template` finds no usable secret and that every required variable has a comment.
- [x] 1.3 Add a startup environment check in `scripts/startup.sh` (or a small Python helper) that refuses to start when required secrets or domains are empty or still placeholders. Verify the container exits non-zero and names the missing variable without printing its value.
- [x] 1.4 Add `.env.local.template` for the `*.pad.test` mode with `CADDYFILE=deploy/Caddyfile.local`, `PAD_DOMAIN=pad.pad.test`, `AUTH_DOMAIN=auth.pad.test`, `CODER_DOMAIN=coder.pad.test` and `COOKIE_DOMAIN=.pad.test`. Verify the values are accepted by `docker compose config`.
- [x] 1.5 Document the environment variable matrix (consumer, production value, local value) in the deployment runbook and verify every variable used by compose appears in the table.
- [x] 1.6 Extend the startup check: when the Coder host is protected in production, fail fast if no shared `COOKIE_DOMAIN` is configured, naming the variable without printing values. Verify the container exits non-zero and the message identifies `COOKIE_DOMAIN`.

## 2. OIDC and session hardening

- [x] 2.1 Replace the fixed `state=default|popup` in `auth_router.py` with a random `state`, a Redis login transaction (`oidc_state:{state}` with mode and `rd`, 10-minute TTL) and an `oidc_state` cookie scoped to `/api/auth`. Verify tests cover valid, missing, mismatched and replayed state.
- [x] 2.2 Add `rd` validation that accepts only local absolute paths or HTTPS URLs on the configured Pad/Coder/Keycloak hosts. Verify tests reject `https://attacker.example`, `//attacker.example`, `http://coder.example.com` and malformed URLs.
- [x] 2.3 Rotate the session identifier at callback and set the session cookie with `Secure`, `HttpOnly`, `SameSite=Lax`, the configured domain and path. Verify a test proves the pre-authentication identifier cannot access the new session.
- [x] 2.4 Add `GET /api/auth/verify` returning `200` with `X-Pad-User`, `X-Pad-Roles` and `X-Pad-Admin`, `302` to login for browser navigation, and `401` JSON for API clients. Redirect only when `Sec-Fetch-Mode: navigate` or `Accept` contains `text/html`; treat `Accept: */*` and `application/json` as API. Verify FastAPI tests cover valid session, expired-refresh, missing session, curl, fetch and navigation, and that the response carries no `Set-Cookie` header and never rotates the session identifier.
- [x] 2.5 Make `/api/auth/logout` idempotent, delete the Redis session and clear the cookie with the same domain/path. Verify a test replays the old cookie after logout and receives `401` from the verify endpoint.
- [x] 2.6 Document the login transaction and logout behavior in the runbook, including how to revoke all sessions by deleting `session:*` keys. Verify the documented Redis command works against the local stack.
- [x] 2.7 Serialize token refresh across `/api/auth/verify` and `/api/auth/refresh` with a per-session lock or coordinator. Verify concurrent requests perform one refresh, the session stays valid and the stored refresh token is not invalidated.
- [x] 2.8 Define and document access-token, refresh-token and cookie lifetimes, including absolute versus idle expiry and the silent re-authentication path when the cookie expires before the Keycloak SSO session. Verify the observed expiry matches the documented values and an expired refresh lifetime returns `401`.

## 3. Application security

- [x] 3.1 Replace `allow_origins=["*"]` in `main.py` with `FRONTEND_URL` and, only in dev mode, `DEV_FRONTEND_URL`. Verify an allowed-origin request receives the origin header and a different origin does not.
- [x] 3.2 Run Uvicorn with `--proxy-headers --forwarded-allow-ips=${TRUSTED_PROXY_IPS}` and set `TRUSTED_PROXY_IPS=*` in compose because Pad is not published. Verify a request through Caddy produces HTTPS redirects and a direct attempt to Pad from outside the private network is refused, so a forged `X-Forwarded-Proto` is never evaluated; document the fixed-Caddy-IP option for deployments that add another proxy.
- [x] 3.3 Split Coder URLs: `coder.py` uses `CODER_INTERNAL_URL`, while `workspace_router.py` and `app_router.py` return `CODER_URL`. Verify the frontend config and workspace `base_url` contain the public host, and backend calls target the internal host.
- [x] 3.4 Split OIDC URLs: `Session.get_auth_url()` uses `OIDC_SERVER_URL`, token and JWKS calls (including `config.get_jwks_client()`) use `OIDC_INTERNAL_URL`, and JWT validation checks the public issuer. Verify a token with a different `iss` is rejected while a correctly issued token is accepted.
- [x] 3.5 Set `CODER_ADDITIONAL_CSP_POLICY=frame-ancestors https://${PAD_DOMAIN}` and `CODER_OIDC_IGNORE_EMAIL_VERIFIED=false` in the production environment. Verify the rendered Coder config contains the Pad origin and not `*`.
- [x] 3.6 Confirm the frontend login redirect and logout flows still work with the gated landing page. Verify a direct request to `/pad/{id}` after login returns to that pad, and logout returns to the Keycloak end-session URL.
- [x] 3.7 Add origin validation for state-changing requests: reject a foreign or missing `Origin`/`Referer` with `403`, keep logout as an idempotent `GET` exception that ignores redirect targets. Verify a same-origin request succeeds and a cross-site request is rejected without modifying data.
- [x] 3.8 Enforce authorized users only: disable Keycloak self-registration and require the configured Pad role, group or allowlist entry before creating a session. Verify an authenticated but unprovisioned user receives `403` with no cookie, while a provisioned user logs in normally.
- [x] 3.9 Add WebSocket authentication: validate the session and `Origin` on handshake, and revalidate the session at an interval no longer than 60 seconds. Verify a cross-origin handshake is rejected, logout closes an open socket within the interval and a removed user loses the socket.

## 4. Caddy configuration

- [x] 4.1 Add `deploy/Caddyfile` (production, ACME email) and `deploy/Caddyfile.local` (`tls internal`) with shared snippets for security headers and `forward_auth`. Verify both pass `caddy fmt` and `caddy validate --config`.
- [x] 4.2 Implement the route matrix: public Pad auth/static paths, protected Pad host, protected Coder host, public Keycloak OIDC paths, protected Keycloak `/admin*`. Verify `curl -i` returns `302`/`401` for anonymous protected paths and `200` for public paths.
- [x] 4.3 Add HSTS, `X-Content-Type-Options`, `Referrer-Policy`, `Permissions-Policy`, a 10 MB request body limit, upstream timeouts and JSON access logs with explicit redaction of `Cookie`, `Authorization`, `code` and `state`. Verify headers are present, a body over the limit returns `413`, and logs contain no cookie, token, code or state value.
- [x] 4.4 Strip `session_id` and client-supplied `X-Pad-*` headers before proxying to Coder and every Keycloak path, and re-add identity headers only from the verify response. Use the same cookie name as `SESSION_COOKIE_NAME`. Verify a request with forged `X-Pad-Admin: true` is not authorized, Coder does not receive the Pad cookie, and a renamed cookie still works.
- [x] 4.5 Document the Caddyfile, the `ADMIN_ALLOWLIST` behavior, local CA trust and certificate troubleshooting in the runbook. Verify the local CA trust command from the runbook makes `curl https://pad.pad.test` succeed without `-k`.
- [x] 4.6 Add the Coder machine-client exception: bypass `forward_auth` only for `/api/v2/*` paths used by the CLI, workspace agents and IDE integrations, and keep the Coder UI gated. Verify a token-authenticated CLI request succeeds without a Pad cookie while the browser UI still redirects to login.
- [x] 4.7 Keep the Keycloak public surface explicit: OIDC endpoints and the account console are reachable without a Pad session, `/admin*` stays gated and registration is disabled. Verify the account console asks for Keycloak login and an unauthenticated admin path is denied.

## 5. Production compose

- [x] 5.1 Add `docker-compose.prod.yml` with `caddy`, `pad`, `postgres`, `redis`, `keycloak` and `coder` on a private bridge network; publish only Caddy's 80/443 ports. Verify `docker compose -f docker-compose.prod.yml config` is valid and no backend service has a `ports` entry.
- [x] 5.2 Add healthchecks, `depends_on` conditions, `restart: unless-stopped`, memory/CPU/PID limits and `json-file` log rotation. Verify `docker compose ps` reports healthy services and `docker inspect` shows the configured limits and log options.
- [x] 5.3 Wire service environment: `POSTGRES_HOST=postgres`, `REDIS_HOST=redis`, `OIDC_INTERNAL_URL=http://keycloak:8080`, `CODER_INTERNAL_URL=http://coder:7080`, `CODER_URL=https://${CODER_DOMAIN}`, `CODER_ACCESS_URL=https://${CODER_DOMAIN}`, Keycloak `KC_DB_URL` to the Keycloak database and Coder `CODER_PG_CONNECTION_URL` to the Coder database. Verify the rendered config contains no production `localhost` service URL.
- [x] 5.4 Add the local test profile (`.env.local`, `deploy/Caddyfile.local`, hosts-file instructions) and start it. Verify the full stack becomes healthy without public DNS or ACME.
- [x] 5.5 Add `scripts/backup-postgres.sh` with timestamped compressed dumps of the Pad, Keycloak and Coder databases and restrictive permissions. Verify every dump can be restored into a scratch database and the script does not print passwords.
- [x] 5.6 Verify the existing development `docker-compose.yml` still works unchanged for local development, or document the required override.
- [x] 5.7 Add a PostgreSQL init script that creates the `pad`, `keycloak` and `coder` databases before services start, and point each service at its own database. Verify all services migrate independently and no service writes into another service's schema.

## 6. Keycloak and Coder integration

- [x] 6.1 Configure the Keycloak realm and confidential client with exact Pad and Coder redirect URIs, exact web origins and an audience mapper; remove wildcard redirects. Verify Pad and Coder login succeed and an unregistered callback is refused.
- [x] 6.2 Configure Coder with the public access URL, public OIDC issuer, internal PostgreSQL URL, Pad-only CSP and verified-email requirement. Verify the Coder UI loads through Caddy and an embedded terminal opens.
- [x] 6.3 Verify Keycloak admin authorization: an `admin` user from an allowed address reaches `/admin`, a non-admin receives `403`, and an `admin` outside the allowlist receives `403`.
- [x] 6.4 Verify session revocation: log out of Pad, then request Coder through Caddy and confirm the request is redirected or rejected, not served from Coder's own session.
- [x] 6.5 End the Coder session on Pad logout: call Coder's logout endpoint or clear its session cookie so a second Pad user on the same browser cannot inherit the first user's Coder session. Verify the user-switch case in the local profile.
- [x] 6.6 Provision the two admin identities separately: the Pad `admin` realm role and the Keycloak administrative permissions, and document the mapping. Verify an `admin` from an allowed IPv4 and IPv6 address reaches `/admin`, while non-admin and out-of-allowlist users receive `403`.

## 7. Documentation and runbook

- [x] 7.1 Write `docs/deployment.md` covering host prerequisites, DNS, firewall, secret generation, Keycloak client setup, Coder template setup, startup order, local test mode, verification checklist, backup/restore and rollback. Verify every command runs as written in the local profile.
- [x] 7.2 Write a security section covering the shared-cookie blast radius, Docker socket host-level risk, fail-closed behavior, residual risks and the recommended trusted-user policy. Verify it states the accepted risk and the follow-up options.
- [x] 7.3 Update `README.md` self-hosting instructions to point to the production runbook and mark the host-networking compose as development-only. Verify a new operator can follow the README to the runbook without encountering the old insecure steps.
- [x] 7.4 Add a smoke-test script or checklist that exercises login, Pad create/open, WebSocket, Coder terminal, admin allow/deny, logout and replay. Verify it runs against the local stack and reports pass/fail per check.
- [x] 7.5 Document the accepted residual risks and follow-up work: Coder static-asset verification cost, image/dependency pinning and vulnerability scanning, preflight across services, backup retention/offsite/encryption, Coder first-user ownership, rate limiting, monitoring, break-glass SSH and secrets in container environment. Verify each item has an owner, a decision and a follow-up reference.

## 8. Acceptance verification

- [ ] 8.1 Execute the automated acceptance suites from section 9 against the local profile and record the result per criterion in `docs/testing.md`. Verify every blocking automated criterion passes.
- [ ] 8.2 Execute the blocking manual staging gates (ACME certificate issuance, clean Debian/Ubuntu install, external port scan, Coder workspace) and record evidence. Verify each gate names the operator, date and environment.
- [ ] 8.3 Run a production readiness dry run: DNS records, certificate issuance, healthchecks, log redaction, resource limits and a backup/restore cycle. Verify the scan shows only 22/80/443 and restore recovers users and pads.
- [ ] 8.4 Measure `forward_auth` latency on an API request and confirm static assets bypass verification. Verify the added latency is acceptable for the target user count and record the result in the runbook.

## 9. Test automation

- [x] 9.1 Add test dependencies and configuration (`requirements-dev.txt`, pytest configuration, frontend test script, Playwright configuration) and `make test-unit|test-integration|test-proxy|test-e2e|test-security|test-deploy|test-all`. Verify each target exists and fails with a clear message when its environment is missing.
- [x] 9.2 Add `compose.test.yml` and a bootstrap script that builds Pad from the working tree, starts the production topology on `*.pad.test` with the internal CA, and waits for health. Verify a clean checkout reaches a healthy stack without public DNS or ACME.
- [x] 9.3 Add a Keycloak realm export with admin, non-admin and unprovisioned test users, exact Pad/Coder redirect URIs, exact web origins, an audience mapper and disabled registration, imported automatically in the test profile. Verify provisioned users can log in, the admin role is present only for the admin user, and the unprovisioned user receives `403`.
- [x] 9.4 Add a Coder bootstrap step (API key, organization, template) for the test profile, or a documented fixture the E2E suite can start a workspace from. Verify the embedded terminal opens in the local profile or record it as a blocking staging gate.
- [x] 9.5 Write unit tests for OIDC state generation and one-time validation, `rd` allowlist, cookie attributes, CORS origin policy, CSRF origin checks, authorization predicate (provisioned user), role/admin derivation, issuer validation and startup configuration guards. Verify the suite passes without PostgreSQL, Redis, Keycloak or Coder.
- [x] 9.6 Write integration tests against real PostgreSQL, Redis and Keycloak for login, callback, session creation, refresh, the refresh race, session lifetime, logout, downstream Coder logout, the verify contract (`200`/`401`/`302`) and revocation. Verify an expired refresh token and a deleted session both fail closed.
- [x] 9.7 Write proxy tests that run only through Caddy: route matrix, public paths, `401` vs `302` content negotiation for curl/fetch/navigation, static assets, unknown Host, forged `X-Pad-*`, cookie stripping on Coder and every Keycloak path, the Coder machine-client token path, `413`, upstream timeout, security headers, log redaction and admin role/IP combinations. Verify no protected test bypasses the edge.
- [x] 9.8 Write security regression tests for foreign CORS origins, missing or foreign `Origin` on state-changing requests, open redirect, session fixation, session replay, header spoofing, unprovisioned users, cross-origin WebSocket handshakes, user switching and direct access to internal ports. Verify every negative case is denied and no session is created or escalated.
- [x] 9.9 Write Playwright E2E tests for first login with return path, Pad create/open, collaboration WebSocket, Coder terminal, logout, Coder logout/user switch, logged-out cookie replay and WebSocket closure after revocation. Verify the suite runs against the local profile; record the Coder terminal as a blocking staging gate only when no template is available.
- [x] 9.10 Write deployment and network checks: compose invariants (private network, no host networking, no backend ports, healthchecks, limits, log rotation), separate service databases, backup/restore of all three databases into fresh volumes, container recreation and certificate persistence, and an external port scan. Verify each check fails on a deliberately broken compose file.
- [x] 9.11 Add `docs/testing.md` with the traceability matrix (criterion ID, spec scenario, test path, type, gate, status), the manual staging gates for ACME, Debian/Ubuntu install and Coder workspace, and the test report template. Verify every blocking scenario from the four behavioral specs has a mapped check.
- [ ] 9.12 Add a CI job that runs the blocking suites on changes to backend auth, Caddy, compose and deployment scripts. Verify a failing suite blocks the workflow and the job does not require public DNS.
- [x] 9.13 Add an explicit machine-client test: `coder` CLI and a workspace agent authenticate with a Coder token through Caddy without a Pad cookie, while the browser UI still redirects to Pad login. Verify the test fails if `/api/v2/*` is put back behind `forward_auth`.
- [x] 9.14 Add commit and workflow linting: Conventional Commits via `commitlint` for commits and PR titles, `actionlint`, and a check that every `uses:` is pinned to a 40-character commit SHA. Verify the lint workflow fails on an unpinned action and on a non-conventional commit.

## Workflow follow-up

- Review the implemented change against the four delta specs.
- Archive the change after the project's review and verification requirements are satisfied.
- Verify the archived specs and the updated deployment documentation.