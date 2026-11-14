# Use Cases

This document is the source of truth for the primary user and operator journeys. Each P0 Use Case has a stable ID, acceptance criteria and a test path. The `use-cases` spec is the normative contract; this document provides the detail and the traceability map.

**P0** = blocking for release. **P1** = required for production but may be a documented staging gate if the environment cannot automate it.

## Catalog

| ID | Actor | Goal | Test | Gate |
| --- | --- | --- | --- | --- |
| UC-01 | User | First login and return to the requested URL | `tests/e2e/specs/uc-01-login.spec.ts` | CI blocking |
| UC-02 | User | Create, edit, switch and persist pads | `tests/e2e/specs/uc-02-pad-persist.spec.ts` | CI blocking |
| UC-03 | Users | Real-time collaboration and reconnect | `tests/e2e/specs/uc-03-collaboration.spec.ts` | CI blocking |
| UC-04 | User | Automatic Coder workspace and terminal | `tests/e2e/specs/uc-04-coder-terminal.spec.ts` | CI blocking; terminal may be staging if no template |
| UC-05 | User | Open code-server through Coder | `tests/e2e/specs/uc-05-code-server.spec.ts` | CI blocking |
| UC-06 | User | Logout, replay rejection and user switch | `tests/e2e/specs/uc-06-logout-revocation.spec.ts` | CI blocking |
| UC-07 | Admin | Keycloak admin access with role and allowlist | `tests/e2e/specs/uc-07-admin.spec.ts` | CI blocking |
| UC-08 | Operator | One-command deployment | `tests/e2e/specs/uc-08-deploy.spec.ts` + `scripts/deploy.sh` | CI + staging |
| UC-09 | Operator | Upgrade and rollback | `tests/deploy/uc-09-upgrade-rollback.sh` | Staging blocking |
| UC-10 | Operator | Backup and restore | `tests/deploy/uc-10-backup-restore.sh` | Staging blocking |

## UC-01 — First login and return path

**Actor:** provisioned user.
**Preconditions:** Pad, Caddy, Keycloak and the `pad` realm are healthy; the user has `pad-user`.
**Main flow:**

1. Open `https://pad.<domain>/pad/<id>` without a session.
2. Caddy redirects to `/api/auth/login?rd=...`.
3. Pad creates a random state and redirects to Keycloak.
4. Keycloak authenticates the user.
5. Pad validates the state, exchanges the code, rotates the session and sets the shared cookie.
6. The browser returns to `/pad/<id>`.

**Alternate/error:** missing/replayed/mismatched state → error, no session; unprovisioned user → 403; Keycloak unavailable → fail closed.

**Expected:** original URL is restored and the Pad session is valid.
**Spec:** `edge-authentication` Protected surfaces, Session verification contract, Redirect after login; `application-security` OIDC state validation.

## UC-02 — Pad create, edit, switch and persist

**Actor:** authenticated user.
**Preconditions:** valid Pad session.
**Main flow:** create a pad, edit the canvas, switch to another tab, return to the first pad, reload.
**Alternate/error:** save checkpoint fails → the user sees an error and the tab switch still occurs; a missing pad returns 404.
**Expected:** the latest scene is present after switching and reloading; the HTTP checkpoint and WS flush both ran.
**Spec:** `use-cases` UC-02; `acceptance-testing` browser E2E.

## UC-03 — Real-time collaboration

**Actor:** two authenticated users.
**Preconditions:** both can access the same pad.
**Main flow:** both open the pad, edit concurrently, receive reconciled elements, lose/restore one WebSocket.
**Alternate/error:** one user loses pad access → the socket closes; reconnect → full resync.
**Expected:** both users converge; no edits are lost.
**Spec:** `edge-gateway` WebSocket proxying; `application-security` WebSocket authentication; `use-cases` UC-03.

## UC-04 — Coder workspace and terminal

**Actor:** provisioned user.
**Preconditions:** Coder healthy, API key valid, default template configured.
**Main flow:** first Pad login creates the Coder user and workspace; Pad state becomes running; embedded terminal iframe uses `workspaceState.agent` (`main`) and connects.
**Alternate/error:** Coder unavailable → dashboard shows a controlled error/503; no template → `409` on start; workspace not ready → starting state.
**Expected:** workspace is created without manual Coder UI steps and the terminal accepts input.
**Spec:** `use-cases` UC-04; `edge-authentication` Coder exceptions; `production-deployment` Coder rotation.

## UC-05 — code-server application

**Actor:** authenticated user.
**Preconditions:** running workspace with the code-server app.
**Main flow:** open `/@<user>/<workspace>.main/apps/code-server/`; Coder session is primed; assets load with correct MIME.
**Alternate/error:** no Coder session → Coder login redirect; Pad session expired → Pad login redirect; missing upstream asset (e.g. `vsda`) is logged but does not block the editor.
**Expected:** editor loads; no 401 from the Pad gate on app assets.
**Spec:** `edge-authentication` explicit Coder exceptions; `use-cases` UC-05.

## UC-06 — Logout, revocation and user switch

**Actor:** user, then a second user on the same browser.
**Preconditions:** both users are provisioned.
**Main flow:** logout deletes the Redis session, clears the Pad cookie and all documented Coder cookies, then reaches Keycloak end-session.
**Alternate/error:** replayed old cookie → 401; Coder cookie remains → user switch must not inherit it.
**Expected:** old cookie and Coder session are invalid; the second user starts clean.
**Spec:** `edge-authentication` Logout ends downstream sessions; `application-security` WebSocket revocation.

## UC-07 — Keycloak admin access

**Actor:** `admin` vs non-admin vs out-of-allowlist admin.
**Preconditions:** admin role in the Pad realm; allowlist configured.
**Main flow:** admin from an allowed address opens `/admin`; Caddy forwards.
**Alternate/error:** non-admin → 403; admin outside allowlist → 403; open allowlist in production → preflight fails.
**Expected:** only admin+allowlist reaches Keycloak admin.
**Spec:** `edge-authentication` Administrative authorization, Production admin allowlist is mandatory.

## UC-08 — One-command deployment

**Actor:** operator.
**Preconditions:** Docker/Compose, DNS for production, secrets available.
**Main flow:** `make deploy PROFILE=local` or `PROFILE=production`; preflight, bootstrap, health, smoke, record.
**Alternate/error:** missing value → fail before start; unhealthy service → stop and print logs; rerun → preserve data.
**Expected:** verified stack or actionable failure.
**Spec:** `deployment-automation` all requirements.

## UC-09 — Upgrade and rollback

**Actor:** operator.
**Preconditions:** recorded digest set and backup.
**Main flow:** `deploy.sh upgrade` selects digests, backs up, applies, verifies; `rollback` restores the previous digest set and backup.
**Alternate/error:** smoke fails → automatic/one-command rollback; backup missing → upgrade refuses.
**Expected:** new release verified or previous release restored.
**Spec:** `deployment-automation` Upgrade and rollback; `ci-cd` Automated rollback.

## UC-10 — Backup and restore

**Actor:** operator.
**Preconditions:** healthy stack; backup target.
**Main flow:** backup all three databases, verify dumps, copy offsite; restore into a fresh volume in staging.
**Alternate/error:** corrupt dump → check fails; restore target not fresh → drill refuses; no offsite copy → operational check fails.
**Expected:** users, pads, realm and Coder state restored; evidence recorded.
**Spec:** `production-deployment` Restore drill, Backup retention and offsite copy.

## Traceability

| Use Case | P0 | Requirements | Automated evidence | Status |
| --- | --- | --- | --- | --- |
| UC-01 | yes | edge-authentication, application-security | `uc-01-login.spec.ts`, integration `test_login_callback.py` | to implement |
| UC-02 | yes | use-cases, acceptance-testing | `uc-02-pad-persist.spec.ts`, existing `pad.spec.ts` | to implement |
| UC-03 | yes | edge-gateway, application-security | `uc-03-collaboration.spec.ts` | to implement |
| UC-04 | yes | edge-authentication, production-deployment | `uc-04-coder-terminal.spec.ts` | to implement |
| UC-05 | yes | edge-authentication | `uc-05-code-server.spec.ts` | to implement |
| UC-06 | yes | edge-authentication, application-security | `uc-06-logout-revocation.spec.ts` | to implement |
| UC-07 | yes | edge-authentication | `uc-07-admin.spec.ts` | to implement |
| UC-08 | yes | deployment-automation | `uc-08-deploy.spec.ts`, deploy checks | to implement |
| UC-09 | yes | deployment-automation, ci-cd | `uc-09-upgrade-rollback.sh` | to implement |
| UC-10 | yes | production-deployment | `uc-10-backup-restore.sh` | to implement |

`docs/testing.md` owns the criterion-level matrix; this table owns the Use Case-level view. A P0 UC with no test or approved gate fails `scripts/check-traceability.py`.
