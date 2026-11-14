import { test, expect } from '@playwright/test';
import {
  keycloakLogin,
  logoutFromPad,
  submitKeycloakCredentials,
  getSecondUserCredentials,
  getBaseUrls,
  getSessionCookieName,
  isOnKeycloakLogin,
} from './helpers';

test.describe('UC-06 logout, revocation and user switch', () => {
  test.beforeEach(async ({ page }) => {
    await keycloakLogin(page);
  });

  test('logout deletes the session and rejects a replayed cookie', async ({ page, context }) => {
    const cookieName = getSessionCookieName();

    const cookiesBefore = await context.cookies();
    const sessionCookie = cookiesBefore.find((c) => c.name === cookieName);
    expect(sessionCookie).toBeDefined();

    await logoutFromPad(page);
    await page.waitForTimeout(1500);

    // Re-add the old session cookie and hit the verify endpoint as an API client.
    await context.addCookies([
      {
        name: sessionCookie!.name,
        value: sessionCookie!.value,
        domain: sessionCookie!.domain,
        path: sessionCookie!.path,
        secure: sessionCookie!.secure,
        httpOnly: sessionCookie!.httpOnly,
        sameSite: (sessionCookie!.sameSite as 'Lax' | 'Strict' | 'None') || 'Lax',
      },
    ]);

    const response = await page.request.get('/api/auth/verify', {
      headers: { Accept: 'application/json' },
    });
    expect(response.status()).toBe(401);
  });

  test('clears documented Coder cookies during logout', async ({ page, context }) => {
    const urls = getBaseUrls();
    const coderDomain = new URL(urls.coder).hostname;

    await context.addCookies([
      { name: 'coder_session_token', value: 'dummy', domain: coderDomain, path: '/', secure: true, httpOnly: true, sameSite: 'Lax' },
      { name: 'coder_oauth_state', value: 'dummy', domain: coderDomain, path: '/', secure: true, httpOnly: true, sameSite: 'Lax' },
      { name: 'oauth_state', value: 'dummy', domain: coderDomain, path: '/', secure: true, httpOnly: true, sameSite: 'Lax' },
      { name: 'oauth_redirect', value: 'dummy', domain: coderDomain, path: '/', secure: true, httpOnly: true, sameSite: 'Lax' },
      { name: 'oauth_pkce_verifier', value: 'dummy', domain: coderDomain, path: '/', secure: true, httpOnly: true, sameSite: 'Lax' },
      { name: 'csrf_token', value: 'dummy', domain: coderDomain, path: '/', secure: true, httpOnly: false, sameSite: 'Lax' },
    ]);

    await logoutFromPad(page);
    await page.waitForTimeout(1500);

    const cookiesAfter = await context.cookies(coderDomain);
    const cleared = ['coder_session_token', 'coder_oauth_state', 'oauth_state', 'oauth_redirect', 'oauth_pkce_verifier', 'csrf_token'];
    for (const name of cleared) {
      const cookie = cookiesAfter.find((c) => c.name === name);
      expect(cookie?.value, `Coder cookie ${name} should be cleared`).toBeFalsy();
    }
  });

  test('a different provisioned user can sign in after logout', async ({ page, context }) => {
    const urls = getBaseUrls();
    const padHostname = new URL(urls.pad).hostname;
    const secondUser = getSecondUserCredentials();

    await logoutFromPad(page);
    await context.clearCookies();

    // Use a unique URL to avoid a bfcache restore of the pre-logout SPA.
    await page.goto(`${urls.pad}/?logged_out=${Date.now()}`);
    await page.waitForLoadState('networkidle');

    expect(isOnKeycloakLogin(page)).toBe(true);
    await submitKeycloakCredentials(page, secondUser.username, secondUser.password);
    await page.waitForURL((url) => url.hostname === padHostname, { timeout: 15000 });

    const status = await page.evaluate(async () => {
      const response = await fetch('/api/auth/status');
      if (!response.ok) throw new Error(`Failed to fetch auth status: ${response.status}`);
      return response.json();
    });

    expect(status.authenticated).toBe(true);
    expect(status.user?.username).toBe(secondUser.username);
  });
});
