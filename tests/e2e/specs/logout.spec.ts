import { test, expect } from '@playwright/test';
import {
  keycloakLogin,
  logoutFromPad,
  submitKeycloakCredentials,
  getTestCredentials,
  getSecondUserCredentials,
  getBaseUrls,
  getSessionCookieName,
  isOnKeycloakLogin,
} from './helpers';

test.describe('logout', () => {
  test.beforeEach(async ({ page }) => {
    await keycloakLogin(page);
  });

  test('ends the session and rejects a replayed cookie', async ({ page, context }) => {
    const urls = getBaseUrls();
    const cookieName = getSessionCookieName();

    // Capture the Pad session cookie before logout.
    const cookiesBefore = await context.cookies();
    const sessionCookie = cookiesBefore.find((c) => c.name === cookieName);
    expect(sessionCookie).toBeDefined();

    // Log out through the UI; the frontend redirects to Keycloak's end-session URL.
    await logoutFromPad(page);

    const finalUrl = page.url();
    const reachedKeycloakLogout =
      finalUrl.includes('/protocol/openid-connect/logout') || finalUrl.includes(urls.auth);
    expect(
      reachedKeycloakLogout,
      `Expected logout to reach Keycloak end-session page, got ${finalUrl}`
    ).toBe(true);

    // Re-add the old session cookie and hit the verify endpoint as an API client.
    await context.addCookies([
      {
        name: sessionCookie.name,
        value: sessionCookie.value,
        domain: sessionCookie.domain,
        path: sessionCookie.path,
        secure: sessionCookie.secure,
        httpOnly: sessionCookie.httpOnly,
        sameSite: (sessionCookie.sameSite as 'Lax' | 'Strict' | 'None') || 'Lax',
      },
    ]);

    const response = await page.request.get('/api/auth/verify', {
      headers: { Accept: 'application/json' },
    });
    expect(response.status()).toBe(401);
  });

  test('allows a different provisioned user to sign in after logout', async ({ page, context }) => {
    const urls = getBaseUrls();
    const padHostname = new URL(urls.pad).hostname;
    const secondUser = getSecondUserCredentials();

    // Log out and clear all cookies (including the Keycloak SSO session)
    // so the next login requires credentials for a different user.
    await logoutFromPad(page);
    await context.clearCookies();

    await page.goto('/');
    await page.waitForLoadState('networkidle');

    expect(isOnKeycloakLogin(page)).toBe(true);
    await submitKeycloakCredentials(page, secondUser.username, secondUser.password);
    await page.waitForURL((url) => url.hostname === padHostname, { timeout: 15000 });

    // Verify the second user's identity through the backend status endpoint.
    const status = await page.evaluate(async () => {
      const response = await fetch('/api/auth/status');
      if (!response.ok) throw new Error(`Failed to fetch auth status: ${response.status}`);
      return response.json();
    });

    expect(status.authenticated).toBe(true);
    expect(status.user?.username).toBe(secondUser.username);
  });
});
