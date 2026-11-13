# Edge-proxy regression tests

This directory contains tests that exercise the public Caddy ingress only.
They never send requests directly to Pad, Keycloak, Coder or the data stores.

## Running

```bash
pytest tests/proxy -m proxy -v
```

The suite skips cleanly when the stack is not reachable.  Start the local
profile first:

```bash
cp .env.local.template .env
# fill secrets, then
docker compose -f docker-compose.prod.yml up -d
```

## Environment variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `PAD_BASE_URL` | `https://pad.pad.test` | Public Pad host through Caddy |
| `AUTH_BASE_URL` | `https://auth.pad.test` | Public Keycloak host through Caddy |
| `CODER_BASE_URL` | `https://coder.pad.test` | Public Coder host through Caddy |
| `CA_BUNDLE` | none | PEM bundle used to verify Caddy's TLS certificate |
| `VERIFY_TLS` | `true` | Set to `false` to disable TLS verification |
| `SESSION_COOKIE_NAME` | `session_id` | Name of the shared session cookie |
| `PAD_TEST_USERNAME` | `admin` | Provisioned test user |
| `PAD_TEST_PASSWORD` | `Password123!` | Password for the provisioned test user |
| `PAD_UNPROVISIONED_USERNAME` | `unprovisioned` | User without Pad roles |
| `SKIP_HEAVY_TESTS` | none | Set to skip the 10 MB body-limit test |

## Scope

* Route matrix: public paths, protected paths, content-negotiated 401/302.
* Coder `/api/v2/*` machine-client exception: no Pad cookie, no 302.
* Keycloak `/realms/*` public surface and `/admin*` protection.
* Forged `X-Pad-*` headers must not grant access.
* Security headers, unknown Host handling and request-body limits.
* Access-log redaction of `session_id`, OIDC `code` and `state`.
