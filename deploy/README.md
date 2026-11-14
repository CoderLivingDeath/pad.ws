# Deployment files

This directory contains the Caddy gateway configuration, database bootstrap, deployment profiles and release manifests used by `scripts/deploy.sh` and `docker-compose.prod.yml`.

## Files

- `Caddyfile` — production gateway. Uses ACME (Let's Encrypt/ZeroSSL) with `{$ACME_EMAIL}`.
- `Caddyfile.local` — local acceptance gateway. Uses Caddy's internal CA for `*.pad.test`.
- `postgres/init/01-databases.sql` — creates the `pad`, `keycloak` and `coder` databases on first PostgreSQL startup.
- `profiles/{local,staging,production}.env` — environment-specific defaults for `scripts/deploy.sh`.
- `releases/<version>.json` — digest-pinned image set for a release.
- `preflight.sh` — compose-wide required-variable and production-guard check.

## Quick start

Use `scripts/deploy.sh` for one-command deployment:

```bash
# Local *.pad.test acceptance mode
make deploy PROFILE=local

# Production (operator must provide domain and allowlist)
make deploy PROFILE=production DOMAIN=example.com ALLOWLIST="203.0.113.0/24"
```

See `docs/deployment.md` for the full runbook.

## Configuration precedence

Resolved configuration follows this order (highest first):

1. CLI flags (`--set KEY=VALUE`, `--domain`, `--allowlist`)
2. Process environment variables
3. `deploy/profiles/<PROFILE>.env`
4. `.env` in the project root
5. Release manifest defaults (`deploy/releases/<version>.json` for image digests)

Run a dry-run to validate configuration without starting containers:

```bash
scripts/deploy.sh up --profile production --domain example.com --allowlist "203.0.113.0/24" --dry-run
```

## Local acceptance profile (`*.pad.test`)

The local profile runs the full production topology on `*.pad.test` using Caddy's internal CA. No public DNS or ACME account is required.

1. Add the three local domains to `/etc/hosts`:

   ```text
   127.0.0.1 pad.pad.test auth.pad.test coder.pad.test
   ```

2. Deploy:

   ```bash
   make deploy PROFILE=local
   ```

3. Trust Caddy's local CA so HTTPS requests succeed without `-k`:

   ```bash
   docker cp caddy:/data/caddy/pki/authorities/local/root.crt /tmp/caddy-root.crt
   sudo cp /tmp/caddy-root.crt /usr/local/share/ca-certificates/caddy-local.crt
   sudo update-ca-certificates
   ```

   On macOS, add the exported certificate to Keychain Access and trust it.

4. Verify the gateway:

   ```bash
   curl -i https://pad.pad.test
   ```

   An unauthenticated browser request should receive a `302` to the Keycloak login page.

## Production profile

1. Create DNS A records for `PAD_DOMAIN`, `AUTH_DOMAIN` and `CODER_DOMAIN` pointing to the host.
2. Open TCP 80 and 443 (and UDP 443 for HTTP/3) in the host firewall.
3. Deploy with an explicit admin allowlist:

   ```bash
   make deploy PROFILE=production DOMAIN=example.com ALLOWLIST="203.0.113.0/24"
   ```

4. Verify health, certificate issuance and the route matrix before cutting over traffic.

## Operator commands

| Command | Purpose |
| --- | --- |
| `make status` | Service health, certificate, backup and Coder key age. |
| `make logs` | Service logs. |
| `make backup` | Back up PostgreSQL databases with integrity checks. |
| `make restore` | Restore databases from the latest dumps. |
| `make rollback` | Roll back to the previous release manifest and backup. |
| `scripts/deploy.sh rotate-key` | Rotate the Coder API key. |
| `scripts/deploy.sh destroy --yes-i-want-to-destroy-data` | Delete the stack and all volumes. |

## Image pinning and rollback

Every production image is referenced by a digest through `${*_IMAGE}` variables. The digest set for each release is recorded in `deploy/releases/<version>.json`. The `upgrade` and `rollback` commands use these manifests to move between reproducible image sets.
