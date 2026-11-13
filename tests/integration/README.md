# Integration tests

These tests exercise the real Pad backend together with PostgreSQL, Redis and
Keycloak.  They are marked with `@pytest.mark.integration` and **must not run
without the compose stack**.

## Running inside the compose network

From the project root, run pytest inside a container attached to the Pad
network.  The exact network name depends on the compose project; the local test
profile uses `pad_pad` by default:

```bash
docker run --rm --network pad_pad -v "$PWD:/app" -w /app python:3.11-slim \
  bash -c "pip install -r requirements-dev.txt -r src/backend/requirements.txt && \
           pytest tests/integration -m integration -v"
```

If the network name differs, replace `pad_pad` with the value shown by
`docker network ls`.

## Required environment variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `PAD_BASE_URL` | `http://pad:8000` | Pad backend address inside the network |
| `OIDC_INTERNAL_URL` | `http://keycloak:8080` | Keycloak internal token/OIDC URL |
| `OIDC_SERVER_URL` | `https://auth.pad.test` | Public Keycloak issuer / auth URL |
| `OIDC_REALM` | `pad` | Keycloak realm |
| `OIDC_CLIENT_ID` | *(required)* | Confidential client ID |
| `OIDC_CLIENT_SECRET` | *(required)* | Confidential client secret |
| `REDIS_HOST` | `redis` | Redis host |
| `REDIS_PORT` | `6379` | Redis port |
| `REDIS_PASSWORD` | *(optional)* | Redis password |
| `FRONTEND_URL` | `https://pad.pad.test` | Public Pad URL used in OIDC redirect URI |

`OIDC_CLIENT_ID` and `OIDC_CLIENT_SECRET` are required; if they are missing the
suite skips with a clear message rather than failing at import time.

## What is covered

- `/api/auth/verify` returns `401` for anonymous API clients and `302` for
  browser navigation.
- `/api/auth/login` redirects to Keycloak with a random, server-side state.
- `/api/auth/callback` rejects missing, mismatched and replayed state values.
- A complete OIDC authorization-code login creates a session in Redis and
  issues the `session_id` cookie.
- `/api/auth/verify` returns `200` with `X-Pad-User`, `X-Pad-Roles` and
  `X-Pad-Admin` headers for a valid session.
- An unusable refresh token causes `/api/auth/refresh` to return `401`.
- `/api/auth/logout` deletes the server-side session and replays of the old
  cookie are rejected.
