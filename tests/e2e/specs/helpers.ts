import { Page, expect } from '@playwright/test';

export interface TestCredentials {
  username: string;
  password: string;
}

export function getTestCredentials(): TestCredentials {
  return {
    username: process.env.PAD_TEST_USERNAME || 'admin',
    password: process.env.PAD_TEST_PASSWORD || 'Password123!',
  };
}

export function getSecondUserCredentials(): TestCredentials {
  return {
    username: process.env.PAD_SECOND_TEST_USERNAME || 'user',
    password: process.env.PAD_SECOND_TEST_PASSWORD || 'Password123!',
  };
}

export function getUnprovisionedCredentials(): TestCredentials {
  return {
    username: process.env.PAD_UNPROVISIONED_USERNAME || 'unprovisioned',
    password: process.env.PAD_UNPROVISIONED_PASSWORD || 'Password123!',
  };
}

export function getBaseUrls() {
  return {
    pad: (process.env.PAD_BASE_URL || 'https://pad.pad.test').replace(/\/$/, ''),
    auth: (process.env.AUTH_BASE_URL || 'https://auth.pad.test').replace(/\/$/, ''),
    coder: (process.env.CODER_BASE_URL || 'https://coder.pad.test').replace(/\/$/, ''),
  };
}

export function getSessionCookieName(): string {
  return process.env.SESSION_COOKIE_NAME || 'session_id';
}

export function uniquePadName(prefix = 'E2E'): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
}

export function isOnKeycloakLogin(page: Page): boolean {
  const url = page.url();
  const urls = getBaseUrls();
  return url.includes('/realms/pad/login') || url.includes(urls.auth);
}

export async function submitKeycloakCredentials(
  page: Page,
  username: string,
  password: string
): Promise<void> {
  await expect(page.locator('input[name="username"]')).toBeVisible({ timeout: 10000 });
  await page.locator('input[name="username"]').fill(username);
  await page.locator('input[name="password"]').fill(password);
  await page.getByRole('button', { name: /sign in/i }).click();
}

/**
 * Navigate to Pad and log in through Keycloak if the browser is redirected.
 * Accepts optional credentials; defaults to PAD_TEST_USERNAME/PAD_TEST_PASSWORD.
 */
export async function keycloakLogin(
  page: Page,
  username?: string,
  password?: string
): Promise<void> {
  const creds = getTestCredentials();
  const user = username ?? creds.username;
  const pass = password ?? creds.password;
  const urls = getBaseUrls();
  const padHostname = new URL(urls.pad).hostname;

  await page.goto('/');
  await page.waitForLoadState('networkidle');

  if (isOnKeycloakLogin(page)) {
    await submitKeycloakCredentials(page, user, pass);
    await page.waitForURL((url) => url.hostname === padHostname, { timeout: 15000 });
  }
}

/**
 * Log out of Pad using the Excalidraw main menu.
 */
export async function logoutFromPad(page: Page): Promise<void> {
  const menuTrigger = page.locator('[aria-label="Menu"], .main-menu-trigger').first();
  await menuTrigger.click();
  const logoutItem = page.getByRole('menuitem', { name: /logout/i });
  await logoutItem.click();
  await page.waitForLoadState('networkidle');
}
