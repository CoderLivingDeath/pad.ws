# Design

## Context

The previous change (`add-caddy-auth-gateway`) is archived and its 54 requirements are now the main specs. The public test stand proves the architecture, but a production-readiness review found blockers: an empty traceability matrix, incomplete CI enforcement, an open admin allowlist, a seven-day Coder key without rotation, undocumented Coder path exceptions, manual deployment, no coverage gates and no Use Case catalog.

This change turns the working test stack into a repeatable delivery system. It does not replace the edge architecture; it hardens it and automates the path from commit to verified deployment.

## Goals / Non-Goals

**Goals:**

- One documented deploy command per profile, idempotent and safe to rerun.
- No manual configuration for local; explicit, validated configuration for production.
- Backend, frontend and Use Case coverage measured and enforced.
- Every P0 user/operator journey has a UC ID and an automated E2E test or an approved staging gate.
- CI verifies changes; CD deploys staging and production with approval and rollback.
- Close the review blockers and document accepted residual risks.

**Non-Goals:**

- Multi-region or high-availability deployment.
- A full monitoring stack (Prometheus/Grafana) in this change; only a health/alert baseline.
- Rootless Docker or a Docker socket proxy; documented follow-up.
- Rate limiting in the standard Caddy build; follow-up or custom build decision.
- Path-based routing on a single host without subdomains.

## Decisions

### D1. One-command deployment script

`scripts/deploy.sh` is the single entry point. It is a thin orchestrator over idempotent steps:

1. Resolve profile and configuration (D2).
2. Run compose-wide preflight (D7).
3. Generate missing secrets and profile files.
4. Start infrastructure (`postgres`, `redis`, `keycloak`, `pad`, `caddy`).
5. Bootstrap Keycloak realm/client (D3).
6. Export the Caddy CA for local; wait for Caddy.
7. Bootstrap Coder key, template and admin workspace (D3).
8. Wait for health and run smoke checks.
9. Record image digests and print URLs/evidence.

Subcommands: `up`, `down`, `destroy`, `status`, `logs`, `backup`, `restore`, `rotate-key`, `upgrade`, `rollback`.

`make deploy PROFILE=local` is a wrapper; `make deploy PROFILE=production DOMAIN=example.com` passes flags. The script is safe to rerun: it reuses secrets, volumes, realm, template and workspace.

Alternatives considered:

- **Keep the manual runbook**: error-prone and the main source of drift. Rejected.
- **Ansible/Terraform for one VPS**: more moving parts than Compose for this scale. Rejected.
- **A hosted control plane**: contradicts self-hosting. Rejected.

### D2. Profiles and configuration precedence

Profiles live in `deploy/profiles/{local,staging,production}.env` and define defaults only. Resolution order:

1. CLI flag (highest)
2. process environment
3. profile file
4. `.env` in the deployment directory
5. safe defaults (lowest)

`local` defaults to `*.pad.test`, internal CA, open admin allowlist and generated test users. `staging` and `production` require explicit `PAD_DOMAIN`, `AUTH_DOMAIN`, `CODER_DOMAIN`, `COOKIE_DOMAIN`, `ADMIN_ALLOWLIST` and `ACME_EMAIL`.

A resolved configuration file is written to a temporary location and validated with `docker compose config`. Secrets are generated once with `openssl rand` and never printed. `deploy/README.md` contains the precedence table and an example for each profile.

### D3. Idempotent Keycloak and Coder bootstrap

- **Keycloak**: import a realm export on a fresh database; on rerun, use Admin REST/`kcadm` to reconcile the client, redirect URIs, roles, scopes and session lifetimes. Never delete an existing realm implicitly.
- **Coder**: obtain an owner session or reuse an admin API key, ensure the `docker` template exists, set `CODER_TEMPLATE_ID`/`CODER_DEFAULT_ORGANIZATION`, create or rotate `CODER_API_KEY` with a recorded creation time, and call `ensure_workspace_exists` for the admin.
- **Workspaces**: Pad's login path already calls `ensure_user_exists`/`ensure_workspace_exists`; the bootstrap only proves the admin path works before traffic.
- Every step checks its result and is safe to repeat. Bootstrap failures stop before Caddy reports the stack ready.

### D4. Coverage tooling and thresholds

| Layer | Tool | Scope | Gate |
| --- | --- | --- | --- |
| Backend | `pytest-cov` | `src/backend` with documented exclusions | 80% lines, 70% branches; 85% lines for auth/session/ws/coder/pad routers |
| Frontend | Vitest + `@vitest/coverage-v8` | `src/frontend/src` | 70% statements/lines, 60% branches, 70% functions; 80% for auth/session/collab |
| E2E | Playwright | P0 Use Cases | 100% UC mapping; no silent skip |

Reports are written to `coverage/backend`, `coverage/frontend` and `coverage/e2e`, uploaded as CI artifacts and summarized in the job. A ratchet compares against `coverage/baseline.json`; more than a one-point drop fails unless explicitly approved.

Exclusions: generated types, vendor bundles, migrations, test fixtures. Each exclusion is listed in `.coveragerc`/Vitest config with a reason.

E2E coverage of browser JavaScript is optional follow-up (`monocart-coverage-reports`); the required gate is Use Case coverage plus backend/frontend coverage.

### D5. Use Case catalog and E2E mapping

`docs/use-cases.md` is the source of truth. Each entry has:

- UC ID, actor, preconditions, main flow, alternate/error flow, expected result.
- Linked requirements from `edge-authentication`, `application-security`, `edge-gateway`, `production-deployment`.
- Test path (`tests/e2e/specs/uc-XX-*.spec.ts`) and gate type (CI blocking, staging, manual).

The P0 set is UC-01…UC-10 from `use-cases` spec. `scripts/check-traceability.py` parses the spec and the document and fails when a P0 UC has no test path or is marked skipped without an approved gate.

### D6. CI quality gates (CD deferred)

`ci.yml` (pull requests and `main`):

- `config`: compose/caddy/actionlint/pin checks.
- `unit`: pytest with coverage.
- `stack`: compose test profile; integration, proxy, security, deploy invariants; backend coverage.
- `e2e`: Playwright UC suites against the stack; frontend coverage if applicable.
- `image`: build on PR, build/publish digest on release tags.
- `quality`: merge coverage, traceability, publish summary.

This change deliberately stops at CI. Automated staging/production deployment and rollback need protected environments, SSH or a self-hosted runner, deploy secrets, backups and a release process; they are a separate change. Until then, deployment and rollback are the explicit operator commands from D1. This matches the current “tests and lints first” scope.

All actions are pinned to commit SHAs; release images are pinned by digest in the release manifest.

### D7. Production hardening decisions

- **Admin allowlist**: `deploy/preflight.sh` rejects `0.0.0.0/0 ::/0`, empty or malformed values when `PROFILE=production`. Local keeps the open allowlist.
- **Logout cookies**: Caddy `/__pad/logout` clears `coder_session_token`, `coder_oauth_state`, `oauth_state`, `oauth_redirect`, `oauth_pkce_verifier` and `csrf_token` on the Coder host; the list is documented and tested with a user switch.
- **Trusted proxy**: a dedicated `edge` network gives Caddy a static address; `TRUSTED_PROXY_IPS` is that address, not `*`. Local may keep `*` only because Pad is unpublished.
- **Image pinning**: `deploy/releases/<version>.json` records Caddy, Pad, PostgreSQL, Redis, Keycloak and Coder digests; compose reads `*_IMAGE` variables.
- **Coder key rotation**: `scripts/rotate-coder-key.sh` creates a new token, updates `.env`, restarts Pad and verifies `/api/workspace/state`. `CODER_API_KEY_CREATED_AT` drives a status warning at six days.
- **Restore**: `scripts/restore-postgres.sh` restores all three databases into a fresh volume; a staging drill is part of acceptance.
- **Monitoring baseline**: `scripts/status.sh` checks container health, certificate expiry, last backup age and Coder key age; optional webhook alert.
- **Backup**: retention via `BACKUP_RETENTION_DAYS` and integrity check with `pg_restore --list`. Offsite copy and encryption are out of scope for this change; they are a documented follow-up (see D9).

### D8. Testability and verification

- Backend route inventory test: FastAPI routes are classified; sensitive routes must depend on `require_auth`/`require_admin`.
- Coverage tests are separate from functional tests so a failing gate is unambiguous.
- The E2E suite is run through Caddy, not direct services.
- The traceability check is a required CI step and a local `make check-traceability` target.
- A staging deploy is the only place where ACME, Debian install, external port scan and real Coder template are exercised; results go into `docs/testing.md`.

### D9. Backup and rate-limiting follow-ups

See `risk-register.md` for the accepted risks, severity, owner and spec links.

**Offsite backup:** the operator chose “nowhere for now”. This change keeps a local timestamped backup with retention and an integrity check. The follow-up options are:

- S3-compatible storage (AWS S3, MinIO, Cloudflare R2, Backblaze B2) via restic/rclone, encrypted and lifecycle-managed;
- an rclone remote (SFTP/WebDAV/Drive);
- an operator-provided path on another host.

They differ in credential model, cost, restore time and encryption. None is implemented now.

**Rate limiting:** the standard `caddy:2-alpine` build has no `rate_limit` directive. Options:

- custom Caddy build with `xcaddy` and a rate-limit plugin, pinned by digest; per-site/per-IP limits and `429`;
- application-level limits in Pad (Redis counters for login/callback/API), plus Keycloak brute-force detection;
- OS-level `nftables`/`iptables` `hashlimit` for coarse protection;
- an external WAF/CDN, which conflicts with the self-hosted single-VPS goal.

Decision: no custom Caddy build in this change. Short-term protection is Keycloak brute-force detection plus documented application-level limits as a follow-up; a custom Caddy build or WAF is a later decision. Rate limiting remains a residual risk, not a hidden requirement.

## Risks / Trade-offs

- **One-command bootstrap touches Keycloak and Coder admin APIs** → idempotent checks, owner-scoped tokens, fail before Caddy reports success, and never delete existing data implicitly.
- **Coverage thresholds can encourage gaming** → exclude only documented generated code, require critical-module thresholds and review coverage diffs.
- **Use Case tests can become flaky** → stable selectors, test IDs, one owner per UC, retries only for E2E, no skip for P0.
- **Pinned digests slow upgrades** → upgrade command is explicit and records the previous set; a stale digest is a deliberate security choice.
- **Static Caddy IP on a Docker network** → compose network must be recreated if the subnet changes; document the subnet and validate it in preflight.
- **CD SSH access to the VPS** → dedicated deploy user, restricted key, protected environment; alternative is a pull-based runner.
- **Monitoring baseline is not full observability** → documented residual risk and follow-up for a metrics stack.

## Migration Plan

1. Archive the previous change and keep its specs as the base (done).
2. Add the new specs and implement the production hardening fixes behind the existing compose file.
3. Add deploy profiles and `scripts/deploy.sh`; verify local on a clean checkout.
4. Add coverage and UC tests; establish the baseline.
5. Add CI checks; make them required.
6. Add CD staging and production; run a staging deploy and a restore drill.
7. Promote the public test stand to the new deploy command; verify and record.
8. Remove the old manual steps from `docs/deployment.md` once the script is verified.

## Resolved Decisions

- **Offsite backup:** not now. Local retention and integrity only; offsite/encryption is a follow-up.
- **CD:** not now. CI runs tests, lints, coverage and traceability; deployment/rollback remain one-command operator actions.
- **Rate limiting:** no custom Caddy build in this change; Keycloak brute-force protection plus documented app-level limits as follow-up.
