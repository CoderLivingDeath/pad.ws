# End-to-end tests

Playwright E2E suite for the primary user journeys through Caddy.

## Prerequisites

1. Start the local acceptance stack:

   ```bash
   scripts/test-env.sh up
   ```

2. Add the local domains to `/etc/hosts`:

   ```text
   127.0.0.1 pad.pad.test auth.pad.test coder.pad.test
   ```

3. Trust the Caddy internal CA so the browser accepts `https://*.pad.test`:

   ```bash
   docker compose -f docker-compose.prod.yml -f compose.test.yml \
     --env-file .env.test cp caddy:/data/caddy/pki/authorities/local/root.crt ./caddy-root.crt
   # Install ./caddy-root.crt in your browser or system trust store.
   ```

4. Test users from `deploy/keycloak/realm-export.json`:

   | Username | Password | Roles |
   | --- | --- | --- |
   | `admin` | `Password123!` | `pad-user`, `admin` |
   | `user` | `Password123!` | `pad-user` |
   | `unprovisioned` | `Password123!` | none |

## Environment variables

| Variable | Default | Description |
| --- | --- | --- |
| `PAD_BASE_URL` | `https://pad.pad.test` | Pad public URL |
| `AUTH_BASE_URL` | `https://auth.pad.test` | Keycloak public URL |
| `CODER_BASE_URL` | `https://coder.pad.test` | Coder public URL |
| `PAD_TEST_USERNAME` | `admin` | Primary test user |
| `PAD_TEST_PASSWORD` | `Password123!` | Primary test user password |
| `PAD_SECOND_TEST_USERNAME` | `user` | Second provisioned test user |
| `PAD_SECOND_TEST_PASSWORD` | `Password123!` | Second test user password |
| `PAD_UNPROVISIONED_USERNAME` | `unprovisioned` | Unprovisioned user |
| `PAD_UNPROVISIONED_PASSWORD` | `Password123!` | Unprovisioned user password |
| `SESSION_COOKIE_NAME` | `session_id` | Name of the Pad session cookie |
| `CODER_E2E` | unset | Set to `1` to run the Coder embedded terminal test |
| `CODER_WORKSPACE_NAME` | `ubuntu` | Workspace name used for the terminal test |

## Run the suite

```bash
cd tests/e2e
npm install
npx playwright test
```

List tests without running them (no running stack required):

```bash
cd tests/e2e
npm install
npx playwright test --list
```

## Notes

- The suite targets Chromium and ignores HTTPS errors for the internal CA.
- The Coder embedded terminal test is skipped by default. It requires a provisioned Coder template and is recorded as a blocking staging gate; set `CODER_E2E=1` to run it.
- Tests exercise the full flow through Caddy: an unauthenticated browser is redirected to Keycloak, logs in, and is returned to Pad.
