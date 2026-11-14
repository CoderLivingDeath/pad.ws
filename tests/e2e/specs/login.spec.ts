import { test, expect } from '@playwright/test';
import {
  keycloakLogin,
  submitKeycloakCredentials,
  getTestCredentials,
  getBaseUrls,
  uniquePadName,
  isOnKeycloakLogin,
} from './helpers';

test.describe('login', () => {
  test('opens Pad without a session, completes Keycloak login, and loads the app', async ({ page }) => {
    await keycloakLogin(page);

    // The Excalidraw canvas and the pad tab bar indicate the SPA has loaded.
    await expect(page.locator('.excalidraw')).toBeVisible({ timeout: 15000 });
    await expect(page.locator('.tabs-bar')).toBeVisible({ timeout: 10000 });
  });

  test('returns to the requested pad URL after logging in', async ({ page, context }) => {
    const creds = getTestCredentials();
    const urls = getBaseUrls();
    const padHostname = new URL(urls.pad).hostname;

    // Start with a fresh session, log in, and create a pad via the backend API
    // using the browser's authenticated cookies.
    await keycloakLogin(page);
    await expect(page.locator('.tabs-bar')).toBeVisible({ timeout: 10000 });

    const pad = await page.evaluate(async () => {
      const response = await fetch('/api/pad/new', { method: 'POST' });
      if (!response.ok) throw new Error(`Failed to create pad: ${response.status}`);
      return response.json();
    });
    expect(pad).toHaveProperty('id');
    const padId = pad.id as string;

    // Rename the pad so we can identify it after the return-path login.
    const newName = uniquePadName('Return');
    await page.evaluate(
      async ({ id, name }) => {
        const response = await fetch(`/api/pad/${id}/rename`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ display_name: name }),
        });
        if (!response.ok) throw new Error(`Failed to rename pad: ${response.status}`);
      },
      { id: padId, name: newName }
    );

    // Log out and clear all cookies so the next visit requires credential entry.
    await page.goto('/api/auth/logout');
    await context.clearCookies();

    // Navigate directly to the pad while logged out; Caddy redirects to Keycloak.
    await page.goto(`/pad/${padId}`);
    await page.waitForLoadState('networkidle');
    expect(isOnKeycloakLogin(page)).toBe(true);

    await submitKeycloakCredentials(page, creds.username, creds.password);
    await page.waitForURL(
      (url) => url.hostname === padHostname && url.pathname.startsWith(`/pad/${padId}`),
      { timeout: 15000 }
    );

    // The browser must end on the requested pad URL and the SPA must load the pad.
    expect(page.url()).toContain(`/pad/${padId}`);
    await expect(page.locator('.tabs-bar')).toBeVisible({ timeout: 10000 });
    await expect(page.getByText(newName)).toBeVisible({ timeout: 10000 });
  });
});
