# Proposal

## Why

The public test stand works, but the production-readiness review found blockers: the traceability matrix is empty, CI does not block changes to the edge/compose configuration, the Keycloak admin allowlist is open, the Coder API key expires after seven days without rotation, and several Coder paths bypass the Pad gate without an explicit threat-model decision. Deployment is still a long manual runbook, tests have no coverage gates, the main user journeys are not written as Use Cases, and CI stops at image build and does not run the tests, lints, coverage and traceability checks.

## What Changes

- Close the production blockers: explicit admin allowlist, Coder key rotation and alerting, complete logout cookie cleanup, trusted-proxy configuration, restore drill, pinned images and a documented Coder bypass threat model.
- Add **one-command deployment** with `scripts/deploy.sh` and profiles (`local`, `staging`, `production`): preflight, secret generation, Keycloak realm import, Coder template/API-key/workspace bootstrap, compose start, health wait, automated smoke checks and rollback.
- Add **flexible configuration**: profile defaults, `.env` overrides, CLI flags and generated production values, with a single documented precedence order and a compose-wide preflight.
- Add **test coverage measurement and gates**: `pytest-cov` for backend, Vitest coverage for frontend, Playwright E2E per Use Case, coverage reports as CI artifacts and a no-regression ratchet.
- Add a **Use Case catalog** (`docs/use-cases.md`) with stable UC IDs, preconditions, steps, expected results and an E2E test for every P0 Use Case.
- Add **CI quality gates**: required config/unit/integration/proxy/security/E2E/coverage/traceability checks, plus digest-recorded image builds. Automated staging/production deployment and rollback are explicitly deferred to a follow-up so this change stays focused on tests and lints.
- Add operational documentation: deployment profiles, upgrade/rollback, key rotation, restore drill, monitoring and residual-risk acceptance.

**BREAKING**: production deployment requires explicit domains, `COOKIE_DOMAIN`, `ADMIN_ALLOWLIST`, Coder credentials and pinned image digests. The default `make deploy` is local/demo mode; production must select the `production` profile.

## Capabilities

### New Capabilities

- `deployment-automation`: one-command idempotent deployment, deploy profiles, configuration precedence, bootstrap of Keycloak/Coder, health verification, upgrade, rollback and destroy.
- `quality-coverage`: backend, frontend and E2E coverage instrumentation, thresholds, reports and no-regression gates.
- `use-cases`: a stable Use Case catalog that defines primary user and operator journeys and binds each P0 Use Case to an automated E2E test.
- `ci-cd`: required tests, lints, coverage and traceability checks, plus image build and release digest recording; automated deployment is follow-up.

### Modified Capabilities

- `edge-authentication`: add production admin-allowlist enforcement, complete downstream logout cleanup and an explicit Coder machine/app path exception model.
- `application-security`: add auditable route authorization, explicit trusted-proxy production configuration and bounded WebSocket revocation.
- `production-deployment`: add Coder credential rotation, restore drill, image digest pinning, operational monitoring and a compose-wide preflight.

## Impact

- **Scripts and tooling**: new `scripts/deploy.sh`, profile/bootstrap helpers, `scripts/rotate-coder-key.sh`, `scripts/restore-postgres.sh`, `scripts/check-traceability.py`, coverage and UC checks; `Makefile` targets.
- **Configuration**: `.env.prod.template`, `.env.local.template`, profile files, `docker-compose.prod.yml`, `compose.test.yml`, Caddy/Keycloak/Coder bootstrap values.
- **Backend**: Coder key metadata and rotation hooks, cookie cleanup, trusted-proxy preflight, route-auth test seam.
- **Frontend**: logout cookie cleanup integration, coverage tooling, E2E test identifiers where needed.
- **Tests**: `pytest-cov`, Vitest coverage, Playwright UC suites, coverage/merge reports, deploy and restore checks.
- **CI**: `.github/workflows/ci.yml`, required checks, artifact and coverage publication. Automated deploy/rollback workflows are follow-up.
- **Docs**: `docs/use-cases.md`, `docs/testing.md`, `docs/deployment.md`, `docs/ci.md`, threat-model/runbook updates and acceptance report.
- **Risk management**: `risk-register.md` with accepted risks, severity, owner, mitigation and links to the governing spec requirements.
- **Images**: digest-pinned Caddy/PostgreSQL/Redis/Keycloak/Coder/Pad references and a recorded rollback set.
