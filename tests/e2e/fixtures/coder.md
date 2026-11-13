# Coder bootstrap fixture for local acceptance tests

Coder must be bootstrapped once per fresh test environment before the E2E
suite can start a workspace. The first Keycloak user to log into Coder becomes
the platform owner, so pick the `admin` test user intentionally.

## Preconditions

- The local stack is healthy: `scripts/test-env.sh status`
- The Caddy internal CA is trusted by your browser (see `scripts/test-env.sh up`)
- The Keycloak realm has been imported with the three test users from
  `deploy/keycloak/realm-export.json`

## Exact steps

### 1. First login and owner account

1. Open https://coder.pad.test in a browser.
2. You are redirected to Pad login, then to Keycloak.
3. Log in with the `admin` test user using the password configured in the
   imported realm.
4. Coder creates the first user as the platform owner.

### 2. API key

1. In Coder, go to **Deployment** → **API keys**.
2. Click **Generate API key**.
3. Copy the token and update `.env.test`:
   ```dotenv
   CODER_API_KEY=<token>
   ```
4. Restart Pad so the backend picks up the key:
   ```bash
   docker compose -f docker-compose.prod.yml -f compose.test.yml \
     --env-file .env.test restart pad
   ```

### 3. Organization ID

1. Go to **Deployment** → **Organizations**.
2. Copy the UUID of the default organization.
3. Update `.env.test`:
   ```dotenv
   CODER_DEFAULT_ORGANIZATION=<uuid>
   ```

### 4. Template

1. Go to **Templates** → **Create template**.
2. Choose **Start from scratch** or import a Docker-based Terraform template.
3. Copy the template UUID.
4. Update `.env.test`:
   ```dotenv
   CODER_TEMPLATE_ID=<uuid>
   ```

### 5. Workspace name

The default workspace name is `ubuntu`. If you prefer a different name, set:

```dotenv
CODER_WORKSPACE_NAME=<name>
```

## Why this is a fixture

Coder's onboarding flow is interactive and the first user becomes owner, so the
E2E suite expects these values to be present in `.env.test`. When they are
missing, `scripts/bootstrap-coder.sh` exits cleanly with a message pointing back
to this document rather than performing destructive operations.
