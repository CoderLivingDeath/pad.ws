# Use Cases

This document is the source of truth for the primary user and operator journeys. Each P0 Use Case has a stable ID, acceptance criteria and a test path. The `use-cases` spec is the normative contract; this document provides the detail and the traceability map.

**P0** = blocking for release. **P1** = required for production but may be a documented staging gate if the environment cannot automate it.

## Catalog

| ID | Actor | Goal | Test | Gate |
| --- | --- | --- | --- | --- |
| UC-01 | User | First login and return to the requested URL | `tests/e2e/specs/uc-01-login.spec.ts` | CI blocking |
| UC-02 | User | Create, edit, switch and persist pads | `tests/e2e/specs/uc-02-pad-persist.spec.ts` | CI blocking |
| UC-03 | Users | Real-time collaboration and reconnect | `tests/e2e/specs/uc-03-collaboration.spec.ts` | CI blocking |
| UC-04 | User | Automatic Coder workspace and terminal | `tests/e2e/specs/uc-04-coder-terminal.spec.ts` | Staging gate (template required) |
| UC-05 | User | Open code-server through Coder | `tests/e2e/specs/uc-05-code-server.spec.ts` | Staging gate (running workspace required) |
| UC-06 | User | Logout, replay rejection and user switch | `tests/e2e/specs/uc-06-logout-revocation.spec.ts` | CI blocking |
| UC-07 | Admin | Keycloak admin access with role and allowlist | `tests/e2e/specs/uc-07-admin.spec.ts` | CI blocking |
| UC-08 | Operator | One-command deployment | `tests/deploy/uc-08-deploy.sh` | CI blocking (dry-run) |
| UC-09 | Operator | Upgrade and rollback | `tests/deploy/uc-09-upgrade-rollback.sh` | Staging gate |
| UC-10 | Operator | Backup and restore | `tests/deploy/uc-10-backup-restore.sh` | Staging gate |

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

**Alternate/error flow:**

- Missing, mismatched or replayed OIDC state → `400` authentication error, no session.
- Unprovisioned user → `403` "not provisioned for Pad access".
- Keycloak unavailable → fail closed (no session).

**Expected result:** the originally requested URL is restored and the Pad session is valid.
**Linked requirements:** `edge-authentication` protected surfaces, session verification contract, redirect after login; `application-security` OIDC state validation.
**Test path:** `tests/e2e/specs/uc-01-login.spec.ts` (successful return path, replayed state rejection, unprovisioned user denial).
**Gate:** CI blocking.

## UC-02 — Pad create, edit, switch and persist

**Actor:** authenticated user.
**Preconditions:** valid Pad session.
**Main flow:**

1. Create a new pad from the tab bar.
2. Edit the scene (add elements).
3. Switch to another pad; the active pad is checkpointed via `PUT /api/pad/{id}/data`.
4. Return to the first pad; the latest elements are loaded.
5. Reload the page; the saved scene is restored from the backend.

**Alternate/error flow:**

- Save checkpoint fails → the user sees a visible error and the tab switch still occurs.
- Missing pad → `404`.

**Expected result:** the latest scene is present after switching and reloading; both the HTTP checkpoint and the collaboration WebSocket flush ran.
**Linked requirements:** `use-cases` UC-02; `acceptance-testing` browser E2E.
**Test path:** `tests/e2e/specs/uc-02-pad-persist.spec.ts`.
**Gate:** CI blocking.

## UC-03 — Real-time collaboration

**Actor:** two authenticated users.
**Preconditions:** both users can access the same pad (owner shares it or the pad is public).
**Main flow:**

1. Both users open the same pad.
2. Both connect to `/ws/pad/{id}`.
3. Edits are published to the Redis stream and received by the other client.
4. One client closes and reopens the WebSocket; it receives the current scene and continues collaborating.

**Alternate/error flow:** one user loses pad access → the socket is closed with `4003`; reconnect attempts are denied until access is restored.

**Expected result:** both users converge; no edits are lost.
**Linked requirements:** `edge-gateway` WebSocket proxying; `application-security` WebSocket authentication; `use-cases` UC-03.
**Test path:** `tests/e2e/specs/uc-03-collaboration.spec.ts`.
**Gate:** CI blocking.

## UC-04 — Coder workspace and terminal

**Actor:** provisioned user.
**Preconditions:** Coder healthy, API key valid, default template configured for full terminal verification.
**Main flow:**

1. First Pad login triggers `coder_api.ensure_user_exists` and `ensure_workspace_exists`.
2. The dashboard polls `/api/workspace/state` and shows `running` or `starting`.
3. The user inserts a terminal embeddable; the iframe loads `/@<user>/<workspace>.main/terminal`.
4. The terminal WebSocket connects to the workspace agent and accepts input.

**Alternate/error flow:**

- Coder unavailable → dashboard shows a controlled error/503.
- No template or no workspace → `/api/workspace/start` returns `409`.
- Workspace not ready → dashboard shows `starting`/`pending`.

**Expected result:** a workspace is created without manual Coder UI steps and the terminal connects when the workspace is running.
**Linked requirements:** `use-cases` UC-04; `edge-authentication` Coder exceptions; `production-deployment` Coder rotation.
**Test path:** `tests/e2e/specs/uc-04-coder-terminal.spec.ts` (automated dashboard/state checks; full terminal is the staging gate).
**Gate:** Staging gate — requires a provisioned Coder template and a running workspace.

## UC-05 — code-server application

**Actor:** authenticated user.
**Preconditions:** running workspace with the code-server app.
**Main flow:**

1. Open `/@<user>/<workspace>.main/apps/code-server/`.
2. Coder session is primed by the Pad-gated browser flow.
3. The editor loads and its static assets are served with correct MIME types.

**Alternate/error flow:**

- No Coder session → Coder redirects to its own login instead of returning an asset `401`.
- Pad session expired → Pad login redirect.
- Missing upstream asset (e.g. `vsda`) is logged but does not block the editor.

**Expected result:** the editor loads; no `401` from the Pad gate on app assets.
**Linked requirements:** `edge-authentication` explicit Coder exceptions; `use-cases` UC-05.
**Test path:** `tests/e2e/specs/uc-05-code-server.spec.ts`.
**Gate:** Staging gate — requires a running workspace with code-server.

## UC-06 — Logout, revocation and user switch

**Actor:** user, then a second user on the same browser.
**Preconditions:** both users are provisioned.
**Main flow:**

1. Logout calls `/api/auth/logout`.
2. Pad deletes the Redis session, clears the shared cookie and publishes `session:revoke:{id}`.
3. The frontend loads `https://coder.<domain>/__pad/logout` in a hidden iframe, clearing every documented Coder cookie.
4. The browser reaches Keycloak end-session.

**Alternate/error flow:**

- Replayed old Pad cookie → `/api/auth/verify` returns `401`.
- Coder cookie remains after logout → the second user must not inherit the first Coder session.

**Expected result:** old Pad and Coder sessions are invalid; the second user starts clean.
**Linked requirements:** `edge-authentication` logout ends downstream sessions; `application-security` WebSocket revocation.
**Test path:** `tests/e2e/specs/uc-06-logout-revocation.spec.ts`.
**Gate:** CI blocking.

## UC-07 — Keycloak admin access

**Actor:** `admin` vs non-admin vs out-of-allowlist admin.
**Preconditions:** admin role in the Pad realm; `ADMIN_ALLOWLIST` configured.
**Main flow:** an admin from an allowed address opens `/admin` on the auth host; Caddy forwards after `pad_auth` and allowlist checks.

**Alternate/error flow:**

- Authenticated non-admin → Caddy returns `403` before Keycloak.
- Admin outside `ADMIN_ALLOWLIST` → Caddy returns `403`.
- Open allowlist (`0.0.0.0/0 ::/0`) in production → `deploy/preflight.sh` rejects it before any container starts.

**Expected result:** only admin+allowlist reaches the Keycloak admin console.
**Linked requirements:** `edge-authentication` administrative authorization, production admin allowlist is mandatory.
**Test path:** `tests/e2e/specs/uc-07-admin.spec.ts` (non-admin denial), `tests/deploy/uc-08-deploy.sh` (open-allowlist preflight rejection).
**Gate:** CI blocking.

## UC-08 — One-command deployment

**Actor:** operator.
**Preconditions:** Docker/Compose available; for production, DNS and secrets are available.
**Main flow:**

1. `make deploy PROFILE=local` or `scripts/deploy.sh up --profile production ...`.
2. `resolve_config` layers CLI > env > profile > `.env` > release manifest defaults.
3. `deploy/preflight.sh` validates required variables and rejects placeholders/open allowlists in production.
4. `docker compose config` validates the resolved configuration.
5. Services start, Keycloak and Coder bootstrap, smoke checks run.
6. The current release manifest is recorded.

**Alternate/error flow:**

- Missing value → fail before any container starts.
- Unhealthy service → command names the failing component and prints recent logs.
- Rerun → data, certificates and secrets are preserved.

**Expected result:** verified stack or actionable failure.
**Linked requirements:** `deployment-automation` all requirements.
**Test path:** `tests/deploy/uc-08-deploy.sh` (dry-run config, preflight success/failure).
**Gate:** CI blocking (dry-run path); full stack bring-up is a manual staging gate recorded by the operator.

## UC-09 — Upgrade and rollback

**Actor:** operator.
**Preconditions:** recorded digest set and backup; staging or production stack running.
**Main flow:**

1. `scripts/deploy.sh upgrade <version>` saves the previous release, creates a pre-upgrade backup, applies the new manifest digests, recreates services and runs smoke checks.
2. `scripts/deploy.sh rollback` restores the previous manifest digests and the recorded database backup, recreates services and runs smoke checks.

**Alternate/error flow:** upgraded stack fails smoke checks → rollback restores the previous release and data.

**Expected result:** new release verified or previous release restored.
**Linked requirements:** `deployment-automation` upgrade and rollback; `ci-cd` automated rollback.
**Test path:** `tests/deploy/uc-09-upgrade-rollback.sh` (digest application, backup-state selection, missing-manifest failure).
**Gate:** Staging gate — full upgrade/rollback with real smoke checks requires a running stack.

## UC-10 — Backup and restore

**Actor:** operator.
**Preconditions:** healthy stack; backup target directory.
**Main flow:**

1. `scripts/deploy.sh backup` dumps `pad`, `keycloak` and `coder` databases.
2. Dumps are integrity-checked with `pg_restore --list`.
3. Old dumps are pruned according to `BACKUP_RETENTION_DAYS`.
4. `scripts/deploy.sh restore --drill` restores into an isolated volume; users, pads, realm and Coder state are available.

**Alternate/error flow:**

- Corrupt dump → integrity check fails and restore refuses.
- Restore target not fresh → drill refuses.
- No offsite copy → operational check fails (recorded risk R-01).

**Expected result:** users, pads, realm and Coder state are restored; evidence is recorded in the testing report.
**Linked requirements:** `production-deployment` restore drill, backup retention and offsite copy.
**Test path:** `tests/deploy/uc-10-backup-restore.sh` (retention, corrupt-dump rejection, isolated restore drill).
**Gate:** Staging gate — full restore into a fresh environment is run in staging.

## Traceability

| Use Case | P0 | Requirements | Automated evidence | Status |
| --- | --- | --- | --- | --- |
| UC-01 | yes | edge-authentication, application-security | `tests/e2e/specs/uc-01-login.spec.ts`, `tests/integration/test_login_callback.py` | green |
| UC-02 | yes | use-cases, acceptance-testing | `tests/e2e/specs/uc-02-pad-persist.spec.ts` | green |
| UC-03 | yes | edge-gateway, application-security | `tests/e2e/specs/uc-03-collaboration.spec.ts` | green |
| UC-04 | yes | edge-authentication, production-deployment | `tests/e2e/specs/uc-04-coder-terminal.spec.ts` | staging gate |
| UC-05 | yes | edge-authentication | `tests/e2e/specs/uc-05-code-server.spec.ts` | staging gate |
| UC-06 | yes | edge-authentication, application-security | `tests/e2e/specs/uc-06-logout-revocation.spec.ts`, `tests/integration/test_logout.py`, `tests/integration/test_ws_revocation.py` | green |
| UC-07 | yes | edge-authentication | `tests/e2e/specs/uc-07-admin.spec.ts`, `tests/proxy/test_routes.py` | green |
| UC-08 | yes | deployment-automation | `tests/deploy/uc-08-deploy.sh`, `tests/deploy/test-config-resolution.sh`, `tests/deploy/run-checks.sh` | green |
| UC-09 | yes | deployment-automation, ci-cd | `tests/deploy/uc-09-upgrade-rollback.sh`, `tests/deploy/test-upgrade-rollback-images.sh`, `tests/deploy/test-upgrade-rollback-state.sh` | staging gate |
| UC-10 | yes | production-deployment | `tests/deploy/uc-10-backup-restore.sh`, `tests/deploy/test-restore-drill.sh`, `tests/deploy/run-checks.sh` | staging gate |

`docs/testing.md` owns the criterion-level matrix; this table owns the Use Case-level view. A P0 UC with no test or approved gate fails `scripts/check-traceability.py`.
