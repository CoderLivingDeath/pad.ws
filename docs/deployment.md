# Deployment Runbook

> This document is a work in progress. Section 1 contains the environment variable matrix; remaining sections will be added in a follow-up task.

## 1. Environment variable matrix

| Variable | Consumer | Production value | Local value |
| --- | --- | --- | --- |
| `PAD_DOMAIN` | Caddy, Pad, Keycloak, Coder | `pad.example.com` | `pad.pad.test` |
| `AUTH_DOMAIN` | Caddy, Keycloak | `auth.example.com` | `auth.pad.test` |
| `CODER_DOMAIN` | Caddy, Pad, Coder | `coder.example.com` | `coder.pad.test` |
| `COOKIE_DOMAIN` | Pad, Caddy | `.example.com` | `.pad.test` |
| `CADDYFILE` | Compose | `deploy/Caddyfile` | `deploy/Caddyfile.local` |
| `ACME_EMAIL` | Caddy | operator email | `local@pad.test` |
| `OIDC_SERVER_URL` | Pad, Coder, Keycloak | `https://auth.example.com` | `https://auth.pad.test` |
| `OIDC_INTERNAL_URL` | Pad | `http://keycloak:8080` (default: `OIDC_SERVER_URL`) | `http://keycloak:8080` |
| `REDIRECT_URI` | Pad | `https://pad.example.com/api/auth/callback` | `https://pad.pad.test/api/auth/callback` |
| `FRONTEND_URL` | Pad, Caddy | `https://pad.example.com` | `https://pad.pad.test` |
| `OIDC_REALM` | Pad, Coder, Keycloak | realm name | `pad` |
| `OIDC_CLIENT_ID` | Pad, Coder | client ID | `pad` |
| `OIDC_CLIENT_SECRET` | Pad, Coder | generated secret | `__CHANGE_ME__` |
| `POSTGRES_USER` | PostgreSQL, Keycloak, Coder, Pad | generated username | `admin` |
| `POSTGRES_PASSWORD` | PostgreSQL, Keycloak, Coder, Pad | generated password | `__CHANGE_ME__` |
| `POSTGRES_DB` | PostgreSQL, Pad | `pad` | `pad` |
| `POSTGRES_HOST` | Pad | `postgres` | `postgres` |
| `POSTGRES_PORT` | Pad | `5432` | `5432` |
| `REDIS_PASSWORD` | Redis, Pad | generated password | `__CHANGE_ME__` |
| `REDIS_HOST` | Pad | `redis` | `redis` |
| `REDIS_PORT` | Pad | `6379` | `6379` |
| `KEYCLOAK_ADMIN` | Keycloak | admin username | `admin` |
| `KEYCLOAK_ADMIN_PASSWORD` | Keycloak | generated password | `__CHANGE_ME__` |
| `KEYCLOAK_DB` | Keycloak | `keycloak` | `keycloak` |
| `CODER_API_KEY` | Pad | generated API key | `__CHANGE_ME__` |
| `CODER_URL` | Pad, Coder | `https://coder.example.com` | `https://coder.pad.test` |
| `CODER_INTERNAL_URL` | Pad | `http://coder:7080` (default: `CODER_URL`) | `http://coder:7080` |
| `CODER_TEMPLATE_ID` | Pad | template UUID | `__CHANGE_ME__` |
| `CODER_DEFAULT_ORGANIZATION` | Pad | organization UUID | `__CHANGE_ME__` |
| `CODER_WORKSPACE_NAME` | Pad | default workspace name | `ubuntu` |
| `CODER_DB` | Coder | `coder` | `coder` |
| `CODER_DB_PASSWORD_URLENCODED` | Coder | URL-encoded password | `__CHANGE_ME__` |
| `DOCKER_GROUP_ID` | Coder | host docker group ID | `__CHANGE_ME__` |
| `ADMIN_ALLOWLIST` | Caddy | operator CIDRs | `0.0.0.0/0 ::/0` |
| `SESSION_COOKIE_NAME` | Pad, Caddy | `session_id` | `session_id` |
| `TRUSTED_PROXY_IPS` | Pad | `*` or fixed Caddy IP | `*` |
| `API_WORKERS` | Pad | `1` | `1` |
| `STATIC_DIR` | Pad | `/app/frontend/dist` | `/app/frontend/dist` |
| `ASSETS_DIR` | Pad | `/app/frontend/dist/assets` | `/app/frontend/dist/assets` |

## 2. Session and token lifetimes

Pad's session layer uses three related lifetimes:

- **Access token lifetime**: dictated by Keycloak (`expires_in` in the token response). Pad caches the token in Redis and refreshes it when it is within 30 seconds of expiry.
- **Refresh token lifetime**: dictated by Keycloak (`refresh_expires_in`). It determines how long a Pad session can remain active without re-authentication. The Redis `session:{id}` key and the browser session cookie both use this value as their `Max-Age` / TTL.
- **Cookie lifetime**: the `session_id` cookie is set with `Max-Age` equal to the refresh lifetime so that the browser can silently re-authenticate through the Keycloak SSO session while the cookie is valid.

When the refresh lifetime ends, `/api/auth/verify` and `/api/auth/refresh` return `401` and the user must log in again. If the cookie expires while the Keycloak SSO session is still valid, the next navigation triggers a new OIDC login that re-authenticates silently and restores the Pad session.
