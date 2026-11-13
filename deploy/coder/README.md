# Coder bootstrap guidance

Coder must be bootstrapped once before it can provision workspaces. The
procedure below is a manual runbook rather than a fragile automated script,
because the first Coder login is interactive and the initial user becomes the
platform owner.

## Before you start

Ensure the stack is healthy:

```bash
docker compose -f docker-compose.prod.yml ps
```

You need:

- a working Keycloak `pad` realm and `pad` confidential client (see
  `deploy/keycloak/README.md`)
- the Coder OIDC client credentials (`OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`)
- the public Coder domain (`CODER_DOMAIN`)

## 1. First login and owner account

1. Open `https://${CODER_DOMAIN}` in a browser.
2. You are redirected to Pad login, then to Keycloak.
3. Log in with the Keycloak user that should own Coder (for example the
   `admin` test user in local mode).
4. Coder creates the first user as the platform owner.

> ⚠️ **First-user becomes owner**: the first Keycloak user to log into Coder
> becomes the Coder owner. Make sure this is the intended operator account.
> Assign additional owners afterward from **Deployment** → **Users** if needed.

## 2. API key

After login, create a provisioner API key:

1. Go to **Deployment** → **API keys**.
2. Click **Generate API key**.
3. Copy the token and store it in `.env` as `CODER_API_KEY`.
4. Restart the Pad container so it can call Coder:
   `docker compose -f docker-compose.prod.yml restart pad`

## 3. Organization ID

If you changed the default organization name, get the organization UUID:

1. Go to **Deployment** → **Organizations**.
2. Copy the UUID of the organization that will own the template.
3. Store it in `.env` as `CODER_DEFAULT_ORGANIZATION`.

## 4. Template

Create or import a Coder template:

1. Go to **Templates** → **Create template**.
2. Choose **Start from scratch** or import a Terraform template.
3. If the template uses Docker, ensure the Coder container can reach the Docker
   socket (`/var/run/docker.sock`) and that the operator understands the
   host-level privilege this grants.
4. Copy the template UUID and store it in `.env` as `CODER_TEMPLATE_ID`.

## 5. Required environment variables

Add the following to `.env`:

```dotenv
CODER_ACCESS_URL=https://${CODER_DOMAIN}
CODER_OIDC_ISSUER_URL=https://${AUTH_DOMAIN}/realms/${OIDC_REALM}
CODER_OIDC_CLIENT_ID=${OIDC_CLIENT_ID}
CODER_OIDC_CLIENT_SECRET=${OIDC_CLIENT_SECRET}
CODER_OIDC_IGNORE_EMAIL_VERIFIED=false
CODER_ADDITIONAL_CSP_POLICY=frame-ancestors https://${PAD_DOMAIN}
```

`CODER_ACCESS_URL` must match the public Coder host so generated workspace
links and OIDC redirects resolve correctly.

`CODER_OIDC_IGNORE_EMAIL_VERIFIED=false` requires every Keycloak user to have
`emailVerified = true` before Coder accepts the OIDC login. This matches the
Pad requirement and prevents unverified test accounts from reaching Coder.

`CODER_ADDITIONAL_CSP_POLICY=frame-ancestors https://${PAD_DOMAIN}` allows the
Pad frontend to embed the Coder terminal in an iframe. Do not use `*` or omit
the Pad origin, or the browser will refuse to render the terminal.

## 6. Restart Coder

After editing `.env`:

```bash
docker compose -f docker-compose.prod.yml up -d --force-recreate coder pad
```

## 7. Verify

1. Log into Pad.
2. Open a pad and insert a terminal element.
3. Confirm the Coder iframe loads and the embedded terminal opens.
4. Confirm `coder ssh` or the Coder CLI can still reach `/api/v2/*` with a
   Coder token and no Pad cookie.

## Why no automated bootstrap

Coder's first-user creation and template import require interactive decisions
(owner account, template choice, Docker template parameters). Automating them
with brittle curl sequences that parse login cookies would break whenever
Coder's onboarding flow changes. A clear runbook is acceptable for a single-VPS,
small-trusted-user deployment.
