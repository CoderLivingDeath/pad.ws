import { test, expect } from '@playwright/test';
import {
  keycloakLogin,
  submitKeycloakCredentials,
  getTestCredentials,
  getUnprovisionedCredentials,
  getBaseUrls,
  getSessionCookieName,
  createPadViaApi,
  isOnKeycloakLogin,
} from './helpers';

test.describe('UC-01 first login and return path', () => {
  test('returns to the requested pad URL after logging in', async ({ page, context }) => {
    const creds = getTestCredentials();
    const urls = getBaseUrls();
    const padHostname = new URL(urls.pad).hostname;

    // Start with a session, create a pad, then log out completely.
    await keycloakLogin(page);
    await expect(page.locator('[data-testid="new-pad-button"]')).toBeVisible({ timeout: 10000 });

    const padId = await createPadViaApi(page, uniquePadName('Return'));

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

    expect(page.url()).toContain(`/pad/${padId}`);
    await expect(page.locator('[data-testid="new-pad-button"]')).toBeVisible({ timeout: 10000 });
  });

  test('rejects a replayed OIDC callback', async ({ page, context }) => {
    const creds = getTestCredentials();
    const urls = getBaseUrls();
    const cookieName = getSessionCookieName();
    let callbackUrl: string | null = null;

    // Capture the callback URL during a normal login so we can replay it later.
    page.on('request', (request) => {
      if (request.method() === 'GET' && request.url().includes('/api/auth/callback')) {
        callbackUrl = request.url();
      }
    });

    await page.goto('/api/auth/login?rd=/');
    await page.waitForLoadState('networkidle');
    await submitKeycloakCredentials(page, creds.username, creds.password);
    await page.waitForURL((url) => url.hostname === new URL(urls.pad).hostname, { timeout: 15000 });

    expect(callbackUrl).toBeTruthy();

    // Log out and clear all cookies (including the OIDC state cookie).
    await page.goto('/api/auth/logout');
    await context.clearCookies();

    // Replay the previously consumed callback URL.
    await page.goto(callbackUrl!);
    await page.waitForLoadState('networkidle');

    const cookies = await context.cookies();
    const sessionCookie = cookies.find((c) => c.name === cookieName);
    expect(sessionCookie, 'replayed callback must not create a Pad session').toBeUndefined();
  });

  test('denies login to an unprovisioned user', async ({ page, context }) => {
    const unprovisioned = getUnprovisionedCredentials();
    let callbackStatus: number | null = null;

    // The callback redirect crosses hosts (auth.* -> pad.*), so observe
    // responses instead of installing a same-origin route.
    page.on('response', (response) => {
      if (response.url().includes('/api/auth/callback')) {
        callbackStatus = response.status();
      }
    });

    await page.goto('/api/auth/login?rd=/');
    await page.waitForLoadState('networkidle');
    await submitKeycloakCredentials(page, unprovisioned.username, unprovisioned.password);
    await page.waitForLoadState('networkidle');

    expect(callbackStatus, 'callback should reject unprovisioned user').toBe(403);

    const cookies = await context.cookies();
    const sessionCookie = cookies.find((c) => c.name === getSessionCookieName());
    expect(sessionCookie, 'unprovisioned user must not receive a session').toBeUndefined();
  });
});

function uniquePadName(prefix = 'E2E'): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
}
