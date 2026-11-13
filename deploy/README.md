# Deployment files

This directory contains the Caddy gateway configuration and database bootstrap used by `docker-compose.prod.yml`.

## Files

- `Caddyfile` — production gateway. Uses ACME (Let's Encrypt/ZeroSSL) with `{$ACME_EMAIL}`.
- `Caddyfile.local` — local acceptance gateway. Uses Caddy's internal CA for `*.pad.test`.
- `postgres/init/01-databases.sql` — creates the `pad`, `keycloak` and `coder` databases on first PostgreSQL startup.

## Local acceptance profile (`*.pad.test`)

The local profile lets you run the full production topology without public DNS or ACME certificates.

1. Copy `.env.local.template` to `.env` and fill in the generated secrets:

   ```bash
   cp .env.local.template .env
   chmod 600 .env
   ```

2. Add the three local domains to `/etc/hosts` (or your resolver):

   ```text
   127.0.0.1 pad.pad.test auth.pad.test coder.pad.test
   ```

3. Start the stack:

   ```bash
   docker compose -f docker-compose.prod.yml --env-file .env up -d
   ```

   The profile selects the local Caddyfile via `CADDYFILE=deploy/Caddyfile.local`.

4. Trust Caddy's local CA so HTTPS requests succeed without `-k`:

   ```bash
   docker cp caddy:/data/caddy/pki/authorities/local/root.crt /tmp/caddy-root.crt
   sudo cp /tmp/caddy-root.crt /usr/local/share/ca-certificates/caddy-local.crt
   sudo update-ca-certificates
   ```

   On macOS, add the exported certificate to Keychain Access and trust it.

5. Verify the gateway responds on HTTPS:

   ```bash
   curl -i https://pad.pad.test
   ```

   An unauthenticated browser request should receive a `302` to the Keycloak login page.

## Production profile

1. Copy `.env.prod.template` to `.env`, fill every `__CHANGE_ME__` value, and set `chmod 600 .env`.
2. Create DNS A records for `PAD_DOMAIN`, `AUTH_DOMAIN` and `CODER_DOMAIN` pointing to the host.
3. Open TCP 80 and 443 (and UDP 443 for HTTP/3) in the host firewall.
4. Start the stack:

   ```bash
   docker compose -f docker-compose.prod.yml up -d
   ```

5. Verify health, certificate issuance and the route matrix before cutting over traffic.
