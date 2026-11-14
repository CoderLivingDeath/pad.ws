# Handoff: production-readiness-and-delivery acceptance

Branch: `wip/production-readiness-and-delivery`
Base: `main` after the deploy/edge/coverage/CI/UC merges.

This note records what is done, what is still open and how to finish the
remaining acceptance work without repeating the investigation. The OpenSpec
task list (`openspec/changes/production-readiness-and-delivery/tasks.md`) stays
the source of truth; this file only explains the state behind it.

## Status

- Tasks: **37/57 complete** at the time of the handoff.
- Unit: 202 passed (backend), 23 passed (frontend, 96.4% lines).
- Integration: 11 passed against the local `*.pad.test` stack.
- Proxy + security: 32 passed, 1 staged skip (Coder machine clients).
- Smoke: 11 passed, 1 skipped (non-admin check when the account is admin).
- E2E: UC-01, UC-02 (create), UC-03 partially green; UC-04/UC-05 skip behind
  documented staging gates; UC-06 still failing; UC-07 has one failing case.
- Traceability: `scripts/check-traceability.py` passes.

## Fixed during acceptance (already committed here)

1. **Caddy logout cookies.** Repeated `header Set-Cookie` overwrote each other,
   so only `csrf_token` was cleared. Switched to `header +Set-Cookie` in both
   Caddyfiles; the proxy test now sees all six cookies.
2. **Caddy static address collision.** Docker assigned `172.28.0.2` to
   `postgres`, so Caddy could not start. All `edge` services now have explicit
   `ipv4_address` values (`caddy .2`, `postgres .3`, `redis .4`, `keycloak .5`,
   `pad .6`, `coder .7`).
3. **CA file permissions.** `caddy-root.crt` was mode `600`; Coder (non-root)
   could not read it and crash-looped with `x509: certificate signed by unknown
   authority`. `test-env.sh`/`deploy.sh` already chmod 644 — keep that.
4. **Preflight could not parse spaced values.** `deploy/preflight.sh` sourced the
   env file, so `ADMIN_ALLOWLIST=0.0.0.0/0 ::/0` ran `::/0` as a command and the
   production guard never fired. Preflight now parses `KEY=VALUE` safely, and
   `deploy.sh` quotes values containing spaces when writing `.env`.
5. **Clean-checkout bootstrap order.** Preflight required
   `CODER_TEMPLATE_ID`/`CODER_DEFAULT_ORGANIZATION`, which only exist after the
   Coder bootstrap. They are validated post-bootstrap now and Pad is recreated to
   pick them up.
6. **Redis pool exhaustion.** `max_connections=20` and each collaboration socket
   holds a blocking stream read plus a pub/sub connection; under E2E load Redis
   returned "Too many connections" and requests failed 401/500. The pool is now
   `REDIS_MAX_CONNECTIONS` (default 100).
7. **Test-only wiring.** `compose.test.yml` mounts `src/backend`,
   `scripts/startup.sh` and `src/frontend/dist` into the Pad container so
   acceptance runs the working tree. `scripts/startup.sh` is now executable.

## Remaining tasks and why they are open

| Task | Blocker / next step |
| --- | --- |
| 1.2 | `rotate-key` needs a live Coder owner session/API key; run `./scripts/deploy.sh rotate-key` on a stack with a bootstrapped Coder and confirm `/api/workspace/state` = 200. |
| 1.8 | Forged `X-Forwarded-Proto` from a non-proxy peer must be proven against the running stack (proxy suite covers the allowed path only). |
| 1.11 | Smoke passes; E2E must pass repeatedly after the UC-06/UC-07 fixes below. |
| 2.4, 2.5, 2.6, 2.7, 2.9 | `scripts/deploy.sh up` end-to-end, Keycloak/Coder bootstrap rerun, upgrade/rollback and failure paths need a stack with a provisioned Coder template. Local acceptance used `test-env.sh`, not `deploy.sh up`. |
| 5.4, 5.8 | GitHub repository admin: branch protection + required checks, then throw-away failing PRs. Steps are in `docs/ci.md`. |
| 6.5, 6.6 | Finish `docs/testing.md` acceptance report (results table) and review `docs/ci.md` after the CI refactor. |
| 7.1–7.8 | Full acceptance run and report: E2E green or staged, restore drill recorded, coverage thresholds recorded, latency measurement, final report. |

## Known failing E2E cases (next debugging steps)

- **UC-02 checkpoint** — `PUT /api/pad/{id}/data` used to return 403 because
  Playwright's request context does not send `Origin`; `apiHeaders()` was added
  and applied. Re-check the remainder (tab switch and reload assertions).
- **UC-06 logout** — the Excalidraw main-menu trigger can be covered by the
  canvas; `logoutFromPad` now clicks it with `force: true`. Verify the menu item
  click actually triggers `/api/auth/logout` and that the replay cookie is
  rejected.
- **UC-07 non-admin** — the spec expects `403` on `https://auth.<domain>/admin/`
  for a non-admin while Pad's `forward_auth` returns `200`. Decide whether the
  correct expectation is `403` from Keycloak or a redirect to login, and align
  the spec with the documented behaviour.
- **UC-04/UC-05** — intentionally skipped through documented staging gates when
  no Coder template/workspace exists. To make them green, bootstrap Coder (2.5)
  and create a template, then remove the skip path.

## How to run the stack again (no stands are running now)

```bash
# 1. Free ports 80/443 (the public stand, if started, must be stopped first).
cd /home/agent/pad-public-test && \
  docker compose -p padpublic -f docker-compose.prod.yml -f compose.public.yml --env-file .env down

# 2. Fresh local acceptance data (realm import and digest-pinned images).
cd /home/agent/pad.ws && chmod 644 caddy-root.crt && \
  docker compose -p padws -f docker-compose.prod.yml -f compose.test.yml --env-file .env.test down -v

# 3. Start (Keycloak's first boot takes ~3 minutes; caddy starts after it is healthy).
bash scripts/test-env.sh up
docker compose -p padws -f docker-compose.prod.yml -f compose.test.yml --env-file .env.test up -d caddy
docker compose -p padws -f docker-compose.prod.yml -f compose.test.yml --env-file .env.test cp \
  caddy:/data/caddy/pki/authorities/local/root.crt ./caddy-root.crt && chmod 644 caddy-root.crt
docker compose -p padws -f docker-compose.prod.yml -f compose.test.yml --env-file .env.test \
  up -d --force-recreate coder   # after the CA copy, otherwise Coder crash-loops

# 4. Build the frontend into the mounted dist when UI specs change.
cd src/frontend && npm ci && npm run build
```

Host entries required: `127.0.0.1 pad.pad.test auth.pad.test coder.pad.test`.

## Environment notes

- The VPS has 3.8 GB RAM and ~2 GB swap. Running the public stand and the local
  acceptance stack together exhausts memory: run one at a time and stop it
  afterwards. Do not leave Playwright or `npm run build` running in the
  background.
- `.env.test` is generated and gitignored; it now carries the `*_IMAGE` values
  and `REDIS_MAX_CONNECTIONS`.
- The public test stand lives in `/home/agent/pad-public-test`; it is a deployed
  copy, not source of truth, and was stopped when this branch was cut.
