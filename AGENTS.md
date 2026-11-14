# AGENTS.md

## Repository shape

- `src/backend` — Python 3.11 / FastAPI. It is copied to `/app` in the image, so imports are **flat** (`from config import ...`, `from routers...`). Run it from `src/backend` or set `PYTHONPATH=src/backend`; do not convert it to a package casually.
- `src/frontend` — React 19 + TypeScript + Vite. The Docker image builds it and Pad serves `dist`; there is no separate frontend server in production.
- `docker-compose.yml` — **development only**: host networking, published DB/cache ports, weak defaults. Never use it on a public host.
- `docker-compose.prod.yml` + `compose.test.yml` + `deploy/` — production/test topology. Only Caddy publishes `80/443`; all other services are internal.
- `openspec/` — OpenSpec planning artifacts. `openspec/changes/archive/2026-11-14-add-caddy-auth-gateway` is archived; its requirements are the main specs. `openspec/changes/production-readiness-and-delivery` is **planning only, 0/57 tasks** — do not implement it without `openspec-apply-change`.

## Commands

Backend unit tests (no local Python deps required):

```bash
docker run --rm -v "$PWD:/app" -w /app python:3.11-slim \
  sh -c "pip install -q -r requirements-dev.txt -r src/backend/requirements.txt && pytest tests/unit -q"
```

Single unit test: append `tests/unit/test_redirect_validation.py -q` (or `-k`). Tests set env in `tests/unit/conftest.py`; `config.py` reads env at import.

Local acceptance stack (`*.pad.test`, internal CA):

```bash
bash scripts/deploy.sh up --profile local
# or the legacy helper:
bash scripts/test-env.sh up
```

The deploy script is the one-command entry point for local, staging and production profiles. It resolves configuration, generates secrets, runs a compose-wide preflight, starts the stack and runs smoke checks. The legacy `scripts/test-env.sh` helper still works for local acceptance.

Both build Pad from the worktree and use ports **80/443**. If a public/test stack is already running on those ports, stop it first. The local profile creates `.env` and `caddy-root.crt`; both are gitignored.

Integration tests (must run inside the Caddy network; script handles it):

```bash
bash scripts/test-integration.sh
# focused: bash scripts/test-integration.sh -k verify
```

Proxy/security and E2E require the stack and host resolution for `pad.pad.test`, `auth.pad.test`, `coder.pad.test`; CI adds `/etc/hosts` and `CA_BUNDLE=$PWD/caddy-root.crt`. See `docs/testing.md` and `tests/proxy/README.md`.

```bash
cd tests/e2e && npm ci && npx playwright install --with-deps chromium && npx playwright test
```

`make test-unit|test-integration|test-proxy|test-e2e|test-security|test-deploy|test-all` are wrappers, but they assume local `pytest`, Node/Playwright and a running test stack. `make test-env` only brings the stack up.

Operator deployment commands:

```bash
make deploy PROFILE=local
make deploy PROFILE=production DOMAIN=example.com ALLOWLIST="203.0.113.0/24"
make status
make logs
make backup
make restore
make rollback
```

Validate a resolved configuration without starting containers:

```bash
bash scripts/deploy.sh up --profile production --domain example.com --allowlist "203.0.113.0/24" --dry-run
```

OpenSpec:

```bash
openspec validate --all
openspec list --json
openspec status --change "production-readiness-and-delivery" --json
```

Do not hand-edit `openspec/specs/**`; archive promotes delta specs. Use `openspec-apply-change` for implementation and `openspec-archive-change` only when tasks and acceptance are complete.

## Auth and proxy invariants

- Caddy is the only public ingress. It calls `GET /api/auth/verify` on Pad. `200` allows; `302` only for browser navigation (`Sec-Fetch-Mode: navigate` or `Accept: text/html`); `401` for API/scripted clients (including `Accept: */*`).
- Sessions live in Redis as `session:<id>`. The cookie is `Secure; HttpOnly; SameSite=Lax` and uses `COOKIE_DOMAIN`; Caddy strips `session_id` before proxying to Coder/Keycloak.
- Do not add public paths casually. Coder intentionally bypasses Pad for `/api/v2/*`, `/derp`, `/derp/*`, `/bin/*`, `/@*` and static assets; Coder authenticates those. Coder UI `/` remains gated.
- Pad scene persistence uses both the collaboration WebSocket and `PUT /api/pad/{id}/data` before tab switches. Do not remove the HTTP checkpoint.
- Coder needs `/bin/coder-linux-amd64` and `/derp` public; without them the workspace agent cannot connect. Coder API keys have a 7-day maximum lifetime.
- Separate PostgreSQL databases: `pad`, `keycloak`, `coder`; Pad tables use schema `pad_ws`. Do not point multiple services at one database.
- Local Coder uses the public issuer through Caddy, `host-gateway`, and the Caddy CA. In production, normal DNS/TLS is enough.

## Testing quirks

- Unit tests must not require PostgreSQL/Redis/Keycloak.
- Integration tests run against real Keycloak/Postgres/Redis through Caddy; they are not host-only.
- E2E user journeys use `@<user>/<workspace>.main/...` — the template agent is `main`, not `agent`.
- Coder may be skipped/gated in E2E when no template is provisioned; do not silently skip P0 Use Cases.
- The code-server `vsda` 404s are upstream; do not mask them in Caddy.
- `tests/e2e/package-lock.json` is committed; use `npm ci`.

## Commits and CI

- Conventional Commits, first line ≤100 chars. Install the hook once: `git config core.hooksPath .githooks`. PR titles are linted because squash merges use them.
- Every `uses:` must be pinned to a 40-character commit SHA; run `./scripts/check-actions-pinned.sh`. `actionlint` runs in CI.
- Workflows: `.github/workflows/ci.yml` (config/unit/stack/e2e), `lint.yml` (commits/actionlint/pins), `docker-build.yml` (image).
- Never commit or print `.env`, `.env.test`, `caddy-root.crt`, backups, `test-results/` or credentials. The public test stand, if present, is a deployed copy outside the repo — treat it as an environment, not source of truth.

## Current gotchas

- `scripts/deploy.sh` and `deploy/profiles/` are now implemented. Use them for new deployments; `scripts/test-env.sh` remains available for local acceptance.
- `docs/testing.md` still has a TBD traceability matrix; `docs/use-cases.md` defines UC-01…UC-10 but the UC tests are not implemented yet.
- `risk-register.md` in the new change records accepted risks (offsite backup, CD, rate limiting).
- If Pad returns `401` after long Coder use, check Keycloak session TTLs; the test realm is configured for 8h idle / 7d max.
- `docker-compose.prod.yml` relies on `*_IMAGE` variables and an `edge` network subnet; always validate generated `.env` files with `docker compose -f docker-compose.prod.yml -f compose.test.yml --env-file .env config` or use `scripts/deploy.sh up ... --dry-run`.
