# Testing and Acceptance Traceability

This document maps every blocking behavioral scenario for the Caddy authentication gateway change to an automated test or a documented manual staging gate.

## Use Case mapping

| Use Case | P0 | Spec scenario | Automated evidence | Gate | Status |
|---|---|---|---|---|---|
| UC-01 | yes | Successful first login | `tests/e2e/specs/uc-01-login.spec.ts` | e2e | green |
| UC-01 | yes | Replayed login is rejected | `tests/e2e/specs/uc-01-login.spec.ts` | e2e | green |
| UC-02 | yes | Changes survive tab switch | `tests/e2e/specs/uc-02-pad-persist.spec.ts` | e2e | green |
| UC-02 | yes | Reload preserves the checkpoint | `tests/e2e/specs/uc-02-pad-persist.spec.ts` | e2e | green |
| UC-03 | yes | Concurrent edits converge | `tests/e2e/specs/uc-03-collaboration.spec.ts` | e2e | green |
| UC-03 | yes | Reconnect resynchronizes | `tests/e2e/specs/uc-03-collaboration.spec.ts` | e2e | green |
| UC-04 | yes | New user gets a workspace | `tests/e2e/specs/uc-04-coder-terminal.spec.ts` | e2e | staging gate |
| UC-04 | yes | Terminal connects | `tests/e2e/specs/uc-04-coder-terminal.spec.ts` | e2e | staging gate |
| UC-05 | yes | code-server loads | `tests/e2e/specs/uc-05-code-server.spec.ts` | e2e | staging gate |
| UC-05 | yes | Unauthorized Coder session is redirected | `tests/e2e/specs/uc-05-code-server.spec.ts` | e2e | green |
| UC-06 | yes | Logout denies replay | `tests/e2e/specs/uc-06-logout-revocation.spec.ts` | e2e | green |
| UC-06 | yes | Second user starts clean | `tests/e2e/specs/uc-06-logout-revocation.spec.ts` | e2e | green |
| UC-07 | yes | Admin is allowed | `tests/e2e/specs/uc-07-admin.spec.ts` | e2e | green |
| UC-07 | yes | Non-admin is denied | `tests/e2e/specs/uc-07-admin.spec.ts` | e2e | green |
| UC-07 | yes | Out-of-allowlist admin is denied | `tests/deploy/uc-08-deploy.sh` | deploy | green |
| UC-08 | yes | Clean deploy succeeds | `tests/deploy/uc-08-deploy.sh` | deploy | green |
| UC-08 | yes | Deploy failure is actionable | `tests/deploy/uc-08-deploy.sh` | deploy | green |
| UC-09 | yes | Upgrade is verified | `tests/deploy/uc-09-upgrade-rollback.sh` | deploy | staging gate |
| UC-09 | yes | Failed upgrade rolls back | `tests/deploy/uc-09-upgrade-rollback.sh` | deploy | staging gate |
| UC-10 | yes | Backup is restorable | `tests/deploy/uc-10-backup-restore.sh` | deploy | staging gate |
| UC-10 | yes | Restore drill is recorded | `tests/deploy/uc-10-backup-restore.sh` | deploy | staging gate |

## Traceability matrix

| Criterion ID | Spec scenario | Test path | Type | Gate | Status |
|---|---|---|---|---|---|
| AUTH-01 | CORS allows only the configured `FRONTEND_URL` | `tests/unit/test_cov_auth_router.py` | unit | CI blocking | green |
| AUTH-02 | CORS does not reflect arbitrary origins | `tests/unit/test_cov_auth_router.py` | unit | CI blocking | green |
| AUTH-03 | OIDC `state` is cryptographically random | `tests/unit/test_oidc_state.py` | unit | CI blocking | green |
| AUTH-04 | OIDC `state` is one-time use | `tests/integration/test_login_callback.py` | integration | CI blocking | green |
| AUTH-05 | Missing or mismatched `state` is rejected | `tests/integration/test_login_callback.py`, `tests/e2e/specs/uc-01-login.spec.ts` | integration / e2e | CI blocking | green |
| AUTH-06 | New session ID issued after login | `tests/integration/test_login_callback.py` | integration | CI blocking | green |
| AUTH-07 | Pre-authentication session identifier is invalidated | `tests/integration/test_login_callback.py` | integration | CI blocking | green |
| AUTH-08 | Session cookie has `Secure`, `HttpOnly`, `SameSite=Lax` | `tests/unit/test_session_cookie.py` | unit | CI blocking | green |
| AUTH-09 | Cookie contains only an opaque identifier | `tests/unit/test_session_cookie.py`, `tests/integration/test_verify.py` | unit / integration | CI blocking | green |
| AUTH-10 | Logout deletes server session and clears cookie | `tests/integration/test_logout.py`, `tests/e2e/specs/uc-06-logout-revocation.spec.ts` | integration / e2e | CI blocking | green |
| AUTH-11 | Forwarded headers are trusted only from Caddy | `tests/proxy/test_routes.py` | proxy | CI blocking | green |
| AUTH-12 | Exact OIDC redirect URIs are registered | `scripts/bootstrap-keycloak.sh`, `tests/e2e/specs/uc-01-login.spec.ts` | integration / e2e | CI blocking | green |
| AUTH-13 | Only provisioned users receive a Pad session | `tests/integration/test_login_callback.py`, `tests/e2e/specs/uc-01-login.spec.ts` | integration / e2e | CI blocking | green |
| AUTH-14 | Pad logout ends the Coder session for the same browser | `tests/e2e/specs/uc-06-logout-revocation.spec.ts`, `tests/proxy/test_routes.py` | e2e / integration | CI blocking | green |
| AUTH-15 | Application logs contain no session secrets | `tests/proxy/test_routes.py` | proxy / security | CI blocking | green |
| AUTH-16 | Token refresh is serialized per session | `tests/integration/test_refresh.py` | integration | CI blocking | green |
| AUTH-17 | Access, refresh and cookie lifetimes are enforced | `tests/integration/test_verify.py` | integration | CI blocking | green |
| PROXY-01 | Pad landing page requires authentication | `tests/proxy/test_routes.py`, `tests/e2e/specs/uc-01-login.spec.ts` | proxy / e2e | CI blocking | green |
| PROXY-02 | Coder UI requires authentication | `tests/proxy/test_routes.py`, `tests/e2e/specs/uc-05-code-server.spec.ts` | proxy / e2e | CI blocking | green |
| PROXY-03 | Keycloak admin requires the `admin` role | `tests/proxy/test_routes.py`, `tests/e2e/specs/uc-07-admin.spec.ts` | proxy | CI blocking | green |
| PROXY-04 | OIDC endpoints remain public | `tests/proxy/test_routes.py` | proxy | CI blocking | green |
| PROXY-05 | Pad static assets are public | `tests/proxy/test_routes.py` | proxy | CI blocking | green |
| PROXY-06 | Anonymous browser is redirected to login | `tests/proxy/test_routes.py`, `tests/e2e/specs/uc-01-login.spec.ts` | proxy / e2e | CI blocking | green |
| PROXY-07 | API receives `401`, not HTML redirect | `tests/proxy/test_routes.py`, `tests/integration/test_verify.py` | proxy | CI blocking | green |
| PROXY-08 | `/api/auth/verify` checks the server-side session | `tests/integration/test_verify.py` | proxy / integration | CI blocking | green |
| PROXY-09 | Expired access token is refreshed | `tests/integration/test_refresh.py` | integration / proxy | CI blocking | green |
| PROXY-10 | Unavailable Pad verification blocks the protected request | `tests/proxy/test_routes.py` | proxy | CI blocking | green |
| PROXY-11 | Client-supplied identity headers are rejected | `tests/proxy/test_routes.py` | proxy / security | CI blocking | green |
| PROXY-12 | Redirect destination is validated against the allowlist | `tests/unit/test_redirect_validation.py`, `tests/e2e/specs/uc-01-login.spec.ts` | unit / integration | CI blocking | green |
| PROXY-13 | Session revocation takes effect on the next request | `tests/integration/test_ws_revocation.py`, `tests/e2e/specs/uc-06-logout-revocation.spec.ts` | integration / proxy | CI blocking | green |
| PROXY-14 | Admin-only paths are protected by role and IP allowlist | `tests/proxy/test_routes.py`, `tests/e2e/specs/uc-07-admin.spec.ts` | proxy | CI blocking | green |
| PROXY-15 | Coder machine clients bypass `forward_auth` on `/api/v2/*` | `tests/proxy/test_machine_clients.py`, `tests/proxy/test_routes.py` | proxy / security | CI blocking | green |
| PROXY-16 | `/api/auth/verify` content negotiation (curl / fetch / navigation) | `tests/integration/test_verify.py`, `tests/proxy/test_routes.py` | proxy / unit | CI blocking | green |
| PROXY-17 | Admin allowlist supports IPv6 | `deploy/preflight.sh`, `tests/deploy/uc-08-deploy.sh` | proxy | CI blocking | green |
| PROXY-18 | Keycloak public surface is explicit | `tests/proxy/test_routes.py` | proxy | CI blocking | green |
| NET-01 | Only Caddy publishes host ports | `tests/deploy/run-checks.sh` | deploy | CI blocking | green |
| NET-02 | PostgreSQL and Redis are unreachable from outside | `tests/deploy/run-checks.sh` | security / deploy | CI blocking | green |
| NET-03 | Pad, Coder and Keycloak native ports are unreachable | `tests/deploy/run-checks.sh` | security / deploy | CI blocking | green |
| NET-04 | All three domains route correctly | `tests/proxy/test_routes.py`, `tests/e2e/specs/uc-01-login.spec.ts` | proxy / e2e | CI blocking | green |
| NET-05 | Unknown `Host` is rejected | `tests/proxy/test_routes.py` | proxy | CI blocking | green |
| NET-06 | TLS works on all domains | `tests/e2e/specs/uc-01-login.spec.ts` | deploy / e2e | staging | not-run |
| NET-07 | HTTP redirects to HTTPS | `tests/proxy/test_routes.py` | proxy / deploy | CI blocking | green |
| NET-08 | Pad WebSocket works through Caddy | `tests/e2e/specs/uc-03-collaboration.spec.ts` | e2e / proxy | CI blocking | green |
| NET-09 | Coder terminal WebSocket works through Caddy | `tests/e2e/specs/uc-04-coder-terminal.spec.ts` | e2e | staging | staging gate |
| NET-10 | Security headers present on all hosts | `tests/proxy/test_routes.py` | proxy | CI blocking | green |
| NET-11 | Pad cannot be framed by a foreign origin | `tests/e2e/specs/uc-01-login.spec.ts`, `tests/proxy/test_routes.py` | e2e / security | CI blocking | green |
| NET-12 | Coder allows framing only by Pad origin | `tests/proxy/test_routes.py` | e2e / security | CI blocking | green |
| NET-13 | Maximum request body size is enforced | `tests/proxy/test_routes.py` | proxy | CI blocking | green |
| NET-14 | Upstream timeout is bounded | `deploy/Caddyfile`, `tests/deploy/run-checks.sh` | proxy | CI blocking | green |
| NET-15 | Access logs contain no secrets | `tests/proxy/test_routes.py` | proxy / deploy | CI blocking | green |
| NET-16 | WebSocket closes after session revocation | `tests/integration/test_ws_revocation.py`, `tests/e2e/specs/uc-06-logout-revocation.spec.ts` | e2e / security | CI blocking | green |
| DEP-01 | Services are on a private bridge network | `tests/deploy/run-checks.sh` | deploy | CI blocking | green |
| DEP-02 | Host networking is absent | `tests/deploy/run-checks.sh` | deploy | CI blocking | green |
| DEP-03 | No working default secrets | `deploy/preflight.sh`, `tests/deploy/uc-08-deploy.sh` | deploy / unit | CI blocking | green |
| DEP-04 | Missing secret blocks production startup | `tests/deploy/uc-08-deploy.sh` | deploy / unit | CI blocking | green |
| DEP-05 | Persistent state survives container recreation | `tests/deploy/test-restore-drill.sh` | deploy | CI blocking | green |
| DEP-06 | PostgreSQL and Redis have healthchecks | `tests/deploy/run-checks.sh` | deploy | CI blocking | green |
| DEP-07 | Pad waits for PostgreSQL and Redis | `docker-compose.prod.yml`, `tests/deploy/run-checks.sh` | deploy | CI blocking | green |
| DEP-08 | Docker log rotation is configured | `tests/deploy/run-checks.sh` | deploy | CI blocking | green |
| DEP-09 | Resource limits are configured | `tests/deploy/run-checks.sh` | deploy | CI blocking | green |
| DEP-10 | Backup produces dumps for every database | `tests/deploy/uc-10-backup-restore.sh`, `scripts/backup-postgres.sh` | deploy | CI blocking | green |
| DEP-11 | Restore recovers users and pads | `tests/deploy/uc-10-backup-restore.sh`, `tests/deploy/test-restore-drill.sh` | deploy | CI blocking | green |
| DEP-12 | Caddy certificates persist across recreation | `tests/deploy/run-checks.sh` | deploy | staging | not-run |
| DEP-13 | Local mode works without public DNS | `tests/deploy/uc-08-deploy.sh`, `tests/e2e/specs/uc-01-login.spec.ts` | deploy / e2e | CI blocking | green |
| DEP-14 | Production works with public domains | `tests/deploy/uc-08-deploy.sh` | deploy | staging | not-run |
| DEP-15 | Docker socket risk is documented | `docs/deployment.md` | manual | staging | not-run |
| DEP-16 | Separate service databases for Pad, Keycloak and Coder | `tests/deploy/run-checks.sh`, `deploy/postgres/init/01-databases.sql` | deploy | CI blocking | green |

## Manual staging gates

The following checks require infrastructure that automated CI cannot reproduce. Each execution must be recorded with operator, date, environment and evidence.

### ACME certificate issuance

- **Scope:** Production deployment with real DNS.
- **Procedure:** Start the stack with `CADDY_TLS=auto`, verify Caddy obtains publicly trusted certificates for `PAD_DOMAIN`, `AUTH_DOMAIN` and `CODER_DOMAIN`, and confirm HTTPS redirect works.
- **Evidence:** Certificate chain output and `curl -I http://<domain>` response.

### Clean Debian/Ubuntu install

- **Scope:** Fresh host with only Docker Engine/Compose installed.
- **Procedure:** Follow `docs/deployment.md` from a clean checkout, configure `.env`, start the stack and log in as admin.
- **Evidence:** Shell transcript or screen recording showing successful first login.

### External port scan

- **Scope:** Staging host with firewall configured.
- **Procedure:** From a second machine, scan the staging host for open ports. Only SSH (22), HTTP (80) and HTTPS (443) may be reachable.
- **Evidence:** `nmap` or equivalent output with operator notes.

### Coder workspace

- **Scope:** Local or staging stack with a provisioned Coder template.
- **Procedure:** Log in through Pad, open a Coder workspace, connect to the embedded terminal and execute a command.
- **Evidence:** Screenshot or terminal transcript. If no template is available, this gate is recorded as blocked rather than skipped.

### Upgrade and rollback

- **Scope:** Staging stack with a previous release recorded.
- **Procedure:** Run `scripts/deploy.sh upgrade <version>`, verify new digests and smoke checks, then run `scripts/deploy.sh rollback` and verify the previous digests and database state are restored.
- **Evidence:** Command output and smoke test summary.

### Backup restore drill

- **Scope:** Staging environment with a fresh database volume.
- **Procedure:** Run `scripts/deploy.sh backup`, then `scripts/deploy.sh restore --drill` into an isolated volume and verify users, pads, realm and Coder state.
- **Evidence:** Restore drill transcript and `pg_restore --list` output.

## Test report template

```
Acceptance test report
======================

Change: production-readiness-and-delivery
Branch:  impl-uc
Date:    YYYY-MM-DD
Operator: <name>
Environment: <local *.pad.test / staging / production>

Summary
-------
Passed:      0
Failed:      0
Not run:     <count>
Blocking:    <count>

Results
-------
| Criterion ID | Result | Notes |
|---|---|---|
| AUTH-01 | passed / failed / not-run | |
| AUTH-02 | passed / failed / not-run | |
| ... | ... | ... |

Use Case results
----------------
| Use Case | Result | Notes |
|---|---|---|
| UC-01 | passed / failed / not-run | |
| UC-02 | passed / failed / not-run | |
| ... | ... | ... |

Manual gates
------------
| Gate | Operator | Date | Environment | Result | Evidence |
|---|---|---|---|---|---|
| ACME certificate issuance | | | | not-run | |
| Debian/Ubuntu install | | | | not-run | |
| External port scan | | | | not-run | |
| Coder workspace | | | | not-run | |
| Upgrade and rollback | | | | not-run | |
| Backup restore drill | | | | not-run | |

Sign-off
--------
Tester: ___________________   Date: _______________
Reviewer: _________________   Date: _______________
```
