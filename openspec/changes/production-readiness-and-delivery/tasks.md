# Tasks

> The previous change `add-caddy-auth-gateway` is archived. Its remaining acceptance items (`8.1–8.4`, `9.12`) are superseded by sections 3–7 of this change.

## 1. Production blockers and hardening

- [ ] 1.1 Add `deploy/preflight.sh` with a compose-wide required-variable check and a production guard that rejects empty, malformed or `0.0.0.0/0 ::/0` `ADMIN_ALLOWLIST`. Verify production startup fails before any container starts; local remains allowed.
- [ ] 1.2 Add `CODER_API_KEY_CREATED_AT` and `scripts/rotate-coder-key.sh` using a Coder owner session/API key. Verify rotation updates `.env`, restarts Pad, revokes the old key and keeps `/api/workspace/state` at 200.
- [ ] 1.3 Extend `scripts/status.sh` with Coder key age (warn at six days), certificate expiry, last backup age and container health. Verify each condition produces a visible failure/exit code.
- [ ] 1.4 Clear every documented Coder cookie in the `/__pad/logout` Caddy route (`coder_session_token`, `coder_oauth_state`, `oauth_state`, `oauth_redirect`, `oauth_pkce_verifier`, `csrf_token`). Verify a second user on the same browser does not inherit the first Coder session.
- [ ] 1.5 Pin Caddy, Pad, PostgreSQL, Redis, Keycloak and Coder images by digest through `${*_IMAGE}` variables and write `deploy/releases/<version>.json`. Verify rollback can start every service from the recorded digest set.
- [ ] 1.6 Add `scripts/restore-postgres.sh` for all three databases with an integrity check (`pg_restore --list`) and a staging drill into a fresh volume. Verify users, pads, realm and Coder state are restored.
- [ ] 1.7 Add backup retention and integrity verification (`BACKUP_RETENTION_DAYS`, `pg_restore --list`). Verify old dumps are pruned and a corrupt dump fails the check. Offsite copy and encryption are follow-up risks R-01/R-02, not part of this change.
- [ ] 1.8 Move Caddy to a dedicated `edge` network with a static address and set `TRUSTED_PROXY_IPS` to that address. Verify a direct request with a forged `X-Forwarded-Proto` is not treated as HTTPS.
- [ ] 1.9 Add a FastAPI route-inventory test that classifies every route as public or protected. Verify a new sensitive route without `require_auth` fails the test.
- [ ] 1.10 Add a log-hygiene test that performs login, callback and logout and inspects Caddy/Pad/Keycloak/Coder logs for cookies, authorization headers, codes, state and Coder keys. Verify no secret is present.
- [ ] 1.11 Fix `scripts/smoke-test.sh` HTML-entity decoding (`&amp;`), the `coder.py` shadowed variable and the flaky E2E return-path selector. Verify smoke and E2E pass repeatedly.
- [ ] 1.12 Reduce WebSocket revalidation to at most 30 seconds and close the socket immediately when the session is revoked. Verify logout closes an open socket.
- [ ] 1.13 Enable Keycloak brute-force protection in the realm export/bootstrap and verify failed login attempts trigger lockout. Record the limits in the risk register.

## 2. One-command deployment

- [ ] 2.1 Add `scripts/deploy.sh` with `up`, `down`, `destroy`, `status`, `logs`, `backup`, `restore`, `rotate-key`, `upgrade` and `rollback` subcommands. Verify `--help` documents every command and destructive teardown requires confirmation.
- [ ] 2.2 Add `deploy/profiles/local.env`, `staging.env` and `production.env` with defaults only. Verify each profile resolves without editing scripts.
- [ ] 2.3 Implement configuration precedence (CLI > environment > profile > `.env` > defaults), write a resolved config and validate it with `docker compose config`. Verify a CLI override wins and a placeholder fails preflight.
- [ ] 2.4 Implement idempotent Keycloak bootstrap: realm import on fresh DB, then reconcile client, redirect URIs, roles, scopes and session lifetimes through Admin REST/`kcadm`. Verify rerun does not duplicate or delete data.
- [ ] 2.5 Implement idempotent Coder bootstrap: template, `CODER_TEMPLATE_ID`, organization, API key and admin workspace. Verify a clean deploy and a rerun both succeed.
- [ ] 2.6 Add health wait and a post-deploy smoke gate. Verify a failed check exits non-zero with the failing component and recent logs.
- [ ] 2.7 Add `upgrade` with pre-deploy backup, digest selection, apply and verification; add `rollback` restoring the previous digest set and backup. Verify both paths against staging.
- [ ] 2.8 Add `make deploy`, `make status`, `make logs`, `make backup`, `make restore`, `make rollback` wrappers. Verify local deploy from a clean checkout with one command.
- [ ] 2.9 Add deploy idempotency and failure tests: rerun on a healthy stack, missing secret, unhealthy service and interrupted bootstrap. Verify data and certificates are preserved on rerun.

## 3. Coverage

- [ ] 3.1 Add `pytest-cov`, `.coveragerc`/`pyproject.toml` coverage configuration and documented exclusions. Verify the backend report is generated and the 80/70/85 thresholds are enforced.
- [ ] 3.2 Add Vitest, `@vitest/coverage-v8` and React Testing Library configuration with 70/60/70 thresholds and 80% for critical auth/session/collab modules.
- [ ] 3.3 Add `make test-coverage` that runs backend and frontend coverage and writes `coverage/backend` and `coverage/frontend`. Verify both reports open locally.
- [ ] 3.4 Add `coverage/baseline.json` and a ratchet check that fails on more than a one-point drop. Verify a deliberately lowered suite fails.
- [ ] 3.5 Add `scripts/check-traceability.py` for requirements, Use Cases and tests. Verify a missing P0 UC or an unmapped blocking scenario fails.
- [ ] 3.6 Add coverage and traceability to CI with artifact upload and a pull-request summary. Verify the summary links the reports and the checks are required.
- [ ] 3.7 Add tests for the uncovered security-critical modules until their thresholds pass: auth/session, verify, Coder API errors, route authorization, WebSocket revocation.
- [ ] 3.8 Add frontend tests for auth/session/collab hooks and critical UI paths until their thresholds pass; document any justified exclusion.

## 4. Use Cases and E2E

- [ ] 4.1 Write `docs/use-cases.md` with UC-01…UC-10: actor, preconditions, main flow, alternate/error flow, expected result, linked requirements, test path and gate. Verify every P0 UC is present.
- [ ] 4.2 Add Playwright specs for user UCs (`uc-01`…`uc-07`) and deployment-harness tests for operator UCs (`tests/deploy/uc-08`…`uc-10`); no P0 test may be silently skipped. Verify the traceability check sees every UC.
- [ ] 4.3 Cover negative/alternate flows for UC-01 (replayed state), UC-06 (replay/user switch), UC-07 (non-admin/out-of-allowlist), UC-08 (failed deploy), UC-09 (failed upgrade rollback).
- [ ] 4.4 Bind UC test results to `docs/testing.md` and `docs/use-cases.md`; verify the traceability checker sees the mapping.
- [ ] 4.5 Add stable `data-testid`/role selectors where needed; remove text-only assertions that cause flakiness. Verify the full E2E suite passes three consecutive runs.

## 5. CI quality gates (CD deferred)

- [ ] 5.1 Refactor `.github/workflows/ci.yml` into `config`, `unit`, `stack`, `e2e`, `quality` and `image` jobs with path filters, concurrency and caching. Verify a Caddy/compose change runs config/proxy/deploy checks.
- [ ] 5.2 Make coverage and traceability required checks; verify a PR with missing coverage or a P0 UC fails.
- [ ] 5.3 Build the Pad image on PR without pushing; publish digest-pinned images on release tags and write the release manifest. Verify the digest is recorded.
- [ ] 5.4 Configure branch protection required checks. Verify a failing lint, unit, coverage or traceability check blocks merge.
- [ ] 5.5 Configure least-privilege CI permissions and registry secrets only; verify PR workflows have no push/deploy credentials and values are masked.
- [ ] 5.6 Publish CI summaries and artifacts: test reports, coverage, image digest and traceability. Verify retention and links.
- [ ] 5.7 Document that staging/production deployment and rollback are manual operator actions in this change and link the CD follow-up. Verify no `cd.yml` deploy workflow is required for acceptance.
- [ ] 5.8 Run a PR with a deliberately failing lint, unit test, coverage threshold and traceability entry; verify each blocks merge.

## 6. Documentation

- [ ] 6.1 Update `docs/deployment.md` for one-command deploy, profiles, configuration precedence and every operator subcommand.
- [ ] 6.2 Document upgrade, rollback, Coder key rotation, restore and destroy with exact commands and expected output.
- [ ] 6.3 Document monitoring, backup retention/offsite/encryption and the alert baseline.
- [ ] 6.4 Document the Coder edge exceptions, admin allowlist model, trusted-proxy boundary and accepted residual risks.
- [ ] 6.5 Update `docs/testing.md` with the real traceability matrix, UC mapping, coverage gates, manual gates and test report template.
- [ ] 6.6 Update `docs/ci.md` with required checks, staging/production promotion, approvals, rollback and secret handling.

## 7. Verification and acceptance

- [ ] 7.1 Deploy locally from a clean checkout with one command and run unit, integration, proxy, security, E2E and coverage suites. Verify every blocking result passes.
- [ ] 7.2 Deploy staging manually with `scripts/deploy.sh` and a real domain/ACME; run an external port scan showing only 22/80/443; record the result.
- [ ] 7.3 Perform a clean Debian/Ubuntu install following only `docs/deployment.md`; verify an operator reaches login, Pad, Coder terminal and code-server.
- [ ] 7.4 Run the restore drill into a fresh environment and record users, pads, realm and Coder state.
- [ ] 7.5 Run all P0 Use Cases through Caddy in CI/staging; verify UC-01…UC-10 are green or have approved staging gates.
- [ ] 7.6 Verify coverage thresholds and the ratchet in CI; record the baseline and the reports.
- [ ] 7.7 Measure `forward_auth` latency and static-asset bypass; record the result in the runbook.
- [ ] 7.8 Record the acceptance report in `docs/testing.md`, close the change tasks and archive after review.
