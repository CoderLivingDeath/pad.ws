import { test, expect } from '@playwright/test';
import { keycloakLogin, getTestCredentials, getBaseUrls } from './helpers';

test.describe('coder', () => {
  test.beforeEach(async ({ page }) => {
    await keycloakLogin(page);
  });

  test('loads the Coder UI through Caddy', async ({ page }) => {
    const urls = getBaseUrls();

    await page.goto(urls.coder);
    await page.waitForLoadState('networkidle');

    // After any OIDC redirect dance, the browser must end on the Coder host.
    await expect(page).toHaveURL(new RegExp(`^${urls.coder}`), { timeout: 30000 });

    // The authenticated Coder dashboard shows either the workspaces heading
    // or a prompt to create a workspace.
    const workspacesHeading = page.locator('h1').filter({ hasText: /workspaces/i }).first();
    const createWorkspaceButton = page.getByRole('button', { name: /create workspace/i });
    await expect(workspacesHeading.or(createWorkspaceButton)).toBeVisible({ timeout: 20000 });
  });

  test('embedded terminal opens when a Coder template is provisioned', async ({ page }) => {
    test.skip(
      !process.env.CODER_E2E,
      'Coder terminal requires CODER_E2E=1 and a provisioned template; this is the documented blocking staging gate'
    );

    const urls = getBaseUrls();
    const creds = getTestCredentials();
    const workspaceName = process.env.CODER_WORKSPACE_NAME || 'ubuntu';
    const terminalUrl = `${urls.coder}/@${creds.username}/${workspaceName}.agent/terminal`;

    await page.goto(terminalUrl);
    await page.waitForLoadState('networkidle');

    // The terminal is ready when the xterm container or the embedding iframe is visible.
    await expect(
      page.locator('.xterm, .xterm-screen, [data-testid="terminal"], iframe[title*="terminal" i]')
    ).toBeVisible({ timeout: 30000 });
  });
});
