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
 * Open the Excalidraw main menu and select Logout.
 */
export async function logoutFromPad(page: Page): Promise<void> {
  await expect(page.locator('[data-testid="new-pad-button"]')).toBeVisible({ timeout: 15000 });
  const menuTrigger = page.getByRole('button', { name: /menu/i }).first();
  await expect(menuTrigger).toBeVisible({ timeout: 5000 });
  await menuTrigger.click();

  const logoutItem = page.locator('[data-testid="logout-menu-item"]');
  await expect(logoutItem).toBeVisible({ timeout: 5000 });
  await logoutItem.click();

  await page.waitForLoadState('networkidle').catch(() => undefined);
}

/**
 * Create a new pad through the authenticated backend API using the browser's cookies.
 */
export async function createPadViaApi(page: Page, name?: string): Promise<string> {
  const pad = await page.evaluate(async () => {
    const response = await fetch('/api/pad/new', { method: 'POST' });
    if (!response.ok) throw new Error(`Failed to create pad: ${response.status}`);
    return response.json();
  });
  expect(pad).toHaveProperty('id');
  const padId = pad.id as string;

  if (name) {
    await page.evaluate(
      async ({ id, displayName }) => {
        const response = await fetch(`/api/pad/${id}/rename`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ display_name: displayName }),
        });
        if (!response.ok) throw new Error(`Failed to rename pad: ${response.status}`);
      },
      { id: padId, displayName: name }
    );
  }

  return padId;
}

/**
 * Fetch the current workspace state through the backend API.
 */
export async function fetchWorkspaceState(page: Page): Promise<{
  id: string;
  state: string;
  name: string;
  username: string;
  base_url: string;
  agent: string;
}> {
  const response = await page.request.get('/api/workspace/state', {
    headers: { Accept: 'application/json' },
  });
  expect(response.ok(), `workspace state failed: ${response.status()}`).toBeTruthy();
  return response.json() as Promise<{
    id: string;
    state: string;
    name: string;
    username: string;
    base_url: string;
    agent: string;
  }>;
}

/**
 * Set a pad's sharing policy through the backend API.
 */
export async function setPadSharingPolicy(
  page: Page,
  padId: string,
  policy: 'private' | 'whitelist' | 'public'
): Promise<void> {
  const response = await page.request.put(`/api/pad/${padId}/sharing`, {
    headers: { 'Content-Type': 'application/json' },
    data: { policy },
  });
  expect(response.ok(), `failed to set sharing policy: ${response.status()}`).toBeTruthy();
}

/**
 * Open a WebSocket to the collaboration endpoint from within the page context.
 * Returns a promise that resolves when the socket opens or rejects on error/timeout.
 */
export function openCollaborationSocket(page: Page, padId: string): Promise<boolean> {
  return page.evaluate(
    (id) =>
      new Promise<boolean>((resolve) => {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const url = `${protocol}//${window.location.host}/ws/pad/${id}`;
        const socket = new WebSocket(url);
        let settled = false;
        const done = (ok: boolean) => {
          if (settled) return;
          settled = true;
          try {
            socket.close();
          } catch {
            // ignore
          }
          resolve(ok);
        };
        socket.onopen = () => done(true);
        socket.onerror = () => done(false);
        socket.onclose = (event) => {
          if (event.code === 1000 || event.code === 1001) done(true);
          else if (!settled) done(false);
        };
        setTimeout(() => done(false), 5000);
      }),
    padId
  );
}
