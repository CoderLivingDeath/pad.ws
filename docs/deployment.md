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
| `CADDY_TLS` | Caddy | `auto` | `internal` |
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
