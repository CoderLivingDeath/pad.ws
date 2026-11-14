import { test, expect } from '@playwright/test';
import { execSync } from 'child_process';
import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';
import {
  keycloakLogin,
  getSecondUserCredentials,
  getBaseUrls,
} from './helpers';

const REPO_ROOT = path.resolve(__dirname, '..', '..', '..');

function makeProductionEnvFile(allowlist: string): string {
  const envPath = path.join(os.tmpdir(), `uc07-preflight-${Date.now()}.env`);
  const content = `
PROFILE=production
PAD_DOMAIN=pad.example.com
AUTH_DOMAIN=auth.example.com
CODER_DOMAIN=coder.example.com
COOKIE_DOMAIN=.example.com
ACME_EMAIL=ops@example.com
CADDYFILE=deploy/Caddyfile
OIDC_SERVER_URL=https://auth.example.com
REDIRECT_URI=https://pad.example.com/api/auth/callback
FRONTEND_URL=https://pad.example.com
OIDC_INTERNAL_URL=http://keycloak:8080
CODER_URL=https://coder.example.com
CODER_INTERNAL_URL=http://coder:7080
OIDC_REALM=pad
OIDC_CLIENT_ID=pad
OIDC_CLIENT_SECRET=secret
POSTGRES_USER=pad
POSTGRES_PASSWORD=secret
POSTGRES_DB=pad
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
REDIS_PASSWORD=secret
REDIS_HOST=redis
REDIS_PORT=6379
KEYCLOAK_ADMIN=admin
KEYCLOAK_ADMIN_PASSWORD=secret
KEYCLOAK_DB=keycloak
CODER_API_KEY=secret
CODER_TEMPLATE_ID=00000000-0000-0000-0000-000000000001
CODER_DEFAULT_ORGANIZATION=00000000-0000-0000-0000-000000000002
CODER_WORKSPACE_NAME=ubuntu
CODER_DB=coder
CODER_DB_PASSWORD_URLENCODED=secret
DOCKER_GROUP_ID=999
ADMIN_ALLOWLIST=${allowlist}
TRUSTED_PROXY_IPS=172.28.0.2
PAD_ALLOWED_ROLES=pad-user
API_WORKERS=1
SESSION_COOKIE_NAME=session_id
STATIC_DIR=/app/frontend/dist
ASSETS_DIR=/app/frontend/dist/assets
BACKUP_RETENTION_DAYS=30
CADDY_IMAGE=caddy:2-alpine@sha256:003a97808e781aa9f7e75cc2f43d34d461099031faf5e20faefb9f61126836f0
POSTGRES_IMAGE=postgres:16@sha256:63e83b5a3dc36a917dccb76fe1bd2ac51f1ec9c1deb47ff20d4f04233bf6eae9
REDIS_IMAGE=redis:7.2-alpine@sha256:a2c8f9d7c49c74ebd2945e3798c71606545c5f0d90d03e9ec4a2bb8d4f56df36
KEYCLOAK_IMAGE=quay.io/keycloak/keycloak:25.0@sha256:82c5b7a110456dbd42b86ea572e728878549954cc8bd03cd65410d75328095d2
CODER_IMAGE=ghcr.io/coder/coder:latest@sha256:77500de63a62f733bb1fbbf79da85e8ad4d6ca582e964f5d6021f46f6dc7fc29
PAD_IMAGE=ghcr.io/pad-ws/pad.ws:main@sha256:0000000000000000000000000000000000000000000000000000000000000000
`;
  fs.writeFileSync(envPath, content.trim(), { mode: 0o600 });
  return envPath;
}

function runDeployDryRun(envPath: string, statePath: string, allowlist: string): { ok: boolean; output: string } {
  try {
    const output = execSync(
      `bash scripts/deploy.sh up --profile production --domain example.com --allowlist "${allowlist}" --set ACME_EMAIL=ops@example.com --dry-run`,
      {
        cwd: REPO_ROOT,
        env: { ...process.env, ENV_FILE: envPath, STATE_DIR: statePath },
        encoding: 'utf-8',
        stdio: 'pipe',
      }
    );
    return { ok: true, output };
  } catch (error: any) {
    return { ok: false, output: (error.stdout?.toString() || '') + (error.stderr?.toString() || '') };
  }
}

test.describe('UC-07 Keycloak admin access', () => {
  test('admin from an allowed address reaches the admin path', async ({ page }) => {
    const urls = getBaseUrls();
    await keycloakLogin(page);

    const response = await page.request.get(`${urls.auth}/admin/`, {
      headers: { Accept: 'text/html' },
      maxRedirects: 0,
    });

    // Caddy must not block the admin; Keycloak may itself redirect to login.
    expect(response.status()).not.toBe(403);
    if (response.status() === 200 || response.status() === 302 || response.status() === 303) {
      expect(response.headers()['content-type'] || '').not.toContain('application/json');
    }
  });

  test('non-admin user is denied from the admin path', async ({ page }) => {
    const urls = getBaseUrls();
    const secondUser = getSecondUserCredentials();
    await keycloakLogin(page, secondUser.username, secondUser.password);

    const response = await page.request.get(`${urls.auth}/admin/`, {
      headers: { Accept: 'text/html' },
      maxRedirects: 0,
    });

    expect(response.status()).toBe(403);
  });

  test('production preflight rejects an open admin allowlist', async () => {
    const envPath = makeProductionEnvFile('0.0.0.0/0 ::/0');
    const statePath = fs.mkdtempSync(path.join(os.tmpdir(), 'uc07-state-'));
    try {
      const { ok, output } = runDeployDryRun(envPath, statePath, '0.0.0.0/0 ::/0');
      expect(ok, `open allowlist should fail preflight, got: ${output}`).toBe(false);
      expect(output).toContain('ADMIN_ALLOWLIST is open');
    } finally {
      fs.unlinkSync(envPath);
      fs.rmSync(statePath, { recursive: true, force: true });
    }
  });
});
