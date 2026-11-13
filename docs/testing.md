# Testing and Acceptance Traceability

This document maps every blocking behavioral scenario for the Caddy authentication gateway change to an automated test or a documented manual staging gate.

## Traceability matrix

| Criterion ID | Spec scenario | Test path | Type | Gate | Status |
|---|---|---|---|---|---|
| AUTH-01 | CORS allows only the configured `FRONTEND_URL` | TBD | unit | CI blocking | TBD |
| AUTH-02 | CORS does not reflect arbitrary origins | TBD | unit | CI blocking | TBD |
| AUTH-03 | OIDC `state` is cryptographically random | TBD | unit | CI blocking | TBD |
| AUTH-04 | OIDC `state` is one-time use | TBD | integration | CI blocking | TBD |
| AUTH-05 | Missing or mismatched `state` is rejected | TBD | integration | CI blocking | TBD |
| AUTH-06 | New session ID issued after login | TBD | integration | CI blocking | TBD |
| AUTH-07 | Pre-authentication session identifier is invalidated | TBD | integration | CI blocking | TBD |
| AUTH-08 | Session cookie has `Secure`, `HttpOnly`, `SameSite=Lax` | TBD | unit / integration | CI blocking | TBD |
| AUTH-09 | Cookie contains only an opaque identifier | TBD | unit | CI blocking | TBD |
| AUTH-10 | Logout deletes server session and clears cookie | TBD | integration | CI blocking | TBD |
| AUTH-11 | Forwarded headers are trusted only from Caddy | TBD | proxy / security | CI blocking | TBD |
| AUTH-12 | Exact OIDC redirect URIs are registered | TBD | integration / e2e | CI blocking | TBD |
| AUTH-13 | Only provisioned users receive a Pad session | TBD | integration / e2e | CI blocking | TBD |
| AUTH-14 | Pad logout ends the Coder session for the same browser | TBD | e2e / integration | CI blocking | TBD |
| AUTH-15 | Application logs contain no session secrets | TBD | integration / security | CI blocking | TBD |
| AUTH-16 | Token refresh is serialized per session | TBD | integration | CI blocking | TBD |
| AUTH-17 | Access, refresh and cookie lifetimes are enforced | TBD | integration | CI blocking | TBD |
| PROXY-01 | Pad landing page requires authentication | TBD | proxy / e2e | CI blocking | TBD |
| PROXY-02 | Coder UI requires authentication | TBD | proxy / e2e | CI blocking | TBD |
| PROXY-03 | Keycloak admin requires the `admin` role | TBD | proxy | CI blocking | TBD |
| PROXY-04 | OIDC endpoints remain public | TBD | proxy | CI blocking | TBD |
| PROXY-05 | Pad static assets are public | TBD | proxy | CI blocking | TBD |
| PROXY-06 | Anonymous browser is redirected to login | TBD | proxy / e2e | CI blocking | TBD |
| PROXY-07 | API receives `401`, not HTML redirect | TBD | proxy | CI blocking | TBD |
| PROXY-08 | `/api/auth/verify` checks the server-side session | TBD | proxy / integration | CI blocking | TBD |
| PROXY-09 | Expired access token is refreshed | TBD | integration / proxy | CI blocking | TBD |
| PROXY-10 | Unavailable Pad verification blocks the protected request | TBD | proxy | CI blocking | TBD |
| PROXY-11 | Client-supplied identity headers are rejected | TBD | proxy / security | CI blocking | TBD |
| PROXY-12 | Redirect destination is validated against the allowlist | TBD | unit / integration | CI blocking | TBD |
| PROXY-13 | Session revocation takes effect on the next request | TBD | integration / proxy | CI blocking | TBD |
| PROXY-14 | Admin-only paths are protected by role and IP allowlist | TBD | proxy | CI blocking | TBD |
| PROXY-15 | Coder machine clients bypass `forward_auth` on `/api/v2/*` | TBD | proxy / security | CI blocking | TBD |
| PROXY-16 | `/api/auth/verify` content negotiation (curl / fetch / navigation) | TBD | proxy / unit | CI blocking | TBD |
| PROXY-17 | Admin allowlist supports IPv6 | TBD | proxy | CI blocking | TBD |
| PROXY-18 | Keycloak public surface is explicit | TBD | proxy | CI blocking | TBD |
| NET-01 | Only Caddy publishes host ports | TBD | deploy | CI blocking | TBD |
| NET-02 | PostgreSQL and Redis are unreachable from outside | TBD | security / deploy | CI blocking | TBD |
| NET-03 | Pad, Coder and Keycloak native ports are unreachable | TBD | security / deploy | CI blocking | TBD |
| NET-04 | All three domains route correctly | TBD | proxy / e2e | CI blocking | TBD |
| NET-05 | Unknown `Host` is rejected | TBD | proxy | CI blocking | TBD |
| NET-06 | TLS works on all domains | TBD | deploy / e2e | staging | TBD |
| NET-07 | HTTP redirects to HTTPS | TBD | proxy / deploy | CI blocking | TBD |
| NET-08 | Pad WebSocket works through Caddy | TBD | e2e / proxy | CI blocking | TBD |
| NET-09 | Coder terminal WebSocket works through Caddy | TBD | e2e | staging | TBD |
| NET-10 | Security headers present on all hosts | TBD | proxy | CI blocking | TBD |
| NET-11 | Pad cannot be framed by a foreign origin | TBD | e2e / security | CI blocking | TBD |
| NET-12 | Coder allows framing only by Pad origin | TBD | e2e / security | CI blocking | TBD |
| NET-13 | Maximum request body size is enforced | TBD | proxy | CI blocking | TBD |
| NET-14 | Upstream timeout is bounded | TBD | proxy | CI blocking | TBD |
| NET-15 | Access logs contain no secrets | TBD | proxy / deploy | CI blocking | TBD |
| NET-16 | WebSocket closes after session revocation | TBD | e2e / security | CI blocking | TBD |
| DEP-01 | Services are on a private bridge network | TBD | deploy | CI blocking | TBD |
| DEP-02 | Host networking is absent | TBD | deploy | CI blocking | TBD |
| DEP-03 | No working default secrets | TBD | deploy / unit | CI blocking | TBD |
| DEP-04 | Missing secret blocks production startup | TBD | deploy / unit | CI blocking | TBD |
| DEP-05 | Persistent state survives container recreation | TBD | deploy | CI blocking | TBD |
| DEP-06 | PostgreSQL and Redis have healthchecks | TBD | deploy | CI blocking | TBD |
| DEP-07 | Pad waits for PostgreSQL and Redis | TBD | deploy | CI blocking | TBD |
| DEP-08 | Docker log rotation is configured | TBD | deploy | CI blocking | TBD |
| DEP-09 | Resource limits are configured | TBD | deploy | CI blocking | TBD |
| DEP-10 | Backup produces dumps for every database | TBD | deploy | CI blocking | TBD |
| DEP-11 | Restore recovers users and pads | TBD | deploy | CI blocking | TBD |
| DEP-12 | Caddy certificates persist across recreation | TBD | deploy | staging | TBD |
| DEP-13 | Local mode works without public DNS | TBD | deploy / e2e | CI blocking | TBD |
| DEP-14 | Production works with public domains | TBD | deploy | staging | TBD |
| DEP-15 | Docker socket risk is documented | TBD | manual | staging | TBD |
| DEP-16 | Separate service databases for Pad, Keycloak and Coder | TBD | deploy | CI blocking | TBD |

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

## Test report template

```
Acceptance test report
======================

Change: add-caddy-auth-gateway
Branch:  ws-test-foundation
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
| ... | ... | |

Manual gates
------------
| Gate | Operator | Date | Environment | Result | Evidence |
|---|---|---|---|---|---|
| ACME certificate issuance | | | | not-run | |
| Debian/Ubuntu install | | | | not-run | |
| External port scan | | | | not-run | |
| Coder workspace | | | | not-run | |

Sign-off
--------
Tester: ___________________   Date: _______________
Reviewer: _________________   Date: _______________
```
