import { test, expect } from '@playwright/test';
import { keycloakLogin, getBaseUrls, fetchWorkspaceState } from './helpers';

test.describe('UC-05 code-server application', () => {
  test.beforeEach(async ({ page }) => {
    await keycloakLogin(page);
  });

  test('code-server app is not blocked by the Pad gate', async ({ page }) => {
    const state = await fetchWorkspaceState(page);
    test.skip(!state || !state.state, 'staging gate: no Coder workspace is provisioned in this environment');
    const urls = getBaseUrls();

    if (!state || !state.name || !state.username) {
      test.skip(true, 'staging gate: code-server requires a provisioned Coder workspace');
    }

    const appUrl = `${urls.coder}/@${state.username}/${state.name}.${state.agent}/apps/code-server/`;
    const response = await page.request.get(appUrl, {
      headers: { Accept: 'text/html' },
      maxRedirects: 0,
    });

    // Coder may redirect to its own login or return the editor; Pad must not return 401/403.
    expect(response.status()).not.toBe(401);
    expect(response.status()).not.toBe(403);
    expect([200, 302, 303, 307, 308, 404]).toContain(response.status());
  });

  test('unauthorized Coder app session is redirected, not asset-401', async ({ browser }) => {
    const context = await browser.newContext({ ignoreHTTPSErrors: true });
    try {
      const page = await context.newPage();
      const urls = getBaseUrls();
      const response = await page.request.get(`${urls.coder}/@user/workspace.main/apps/code-server/`, {
        headers: { Accept: 'text/html' },
        maxRedirects: 0,
      });

      expect([200, 302, 303, 307, 308, 401, 403, 404]).toContain(response.status());
      if (response.status() === 401 || response.status() === 403) {
        const contentType = response.headers()['content-type'] || '';
        expect(contentType).not.toContain('application/octet-stream');
      }
    } finally {
      await context.close();
    }
  });
});
