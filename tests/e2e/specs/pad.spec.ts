import { test, expect } from '@playwright/test';
import { keycloakLogin } from './helpers';

test.describe('pad', () => {
  test.beforeEach(async ({ page }) => {
    await keycloakLogin(page);
  });

  test('creates a pad from the UI, opens it, and connects to its collaboration WebSocket', async ({ page }) => {
    await expect(page.locator('.tabs-bar')).toBeVisible({ timeout: 10000 });

    // Create a new pad from the tab bar's "New pad" button.
    await page.locator('.new-tab-button-container button').click();

    // The new pad should become the active tab.
    await expect(page.locator('.active-pad .tab-title')).toContainText('New pad', { timeout: 10000 });

    // The Excalidraw editor / canvas should be visible.
    await expect(page.locator('.excalidraw')).toBeVisible({ timeout: 15000 });

    // Discover the active pad id from the authenticated user profile.
    const padId = await page.evaluate(async () => {
      const response = await fetch('/api/users/me');
      if (!response.ok) throw new Error(`Failed to fetch user profile: ${response.status}`);
      const data = await response.json();
      return (data.last_selected_pad || data.pads?.[0]?.id) as string;
    });
    expect(padId).toBeTruthy();

    // Open a same-origin WebSocket to the collaboration endpoint from the page.
    const wsOpened = await page.evaluate(async (id) => {
      return new Promise<boolean>((resolve) => {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const url = `${protocol}//${window.location.host}/ws/pad/${id}`;
        const socket = new WebSocket(url);

        const done = (ok: boolean) => {
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
          // Normal closure codes count as a successful open+close.
          if (event.code === 1000 || event.code === 1001) done(true);
        };

        // Timeout if the handshake never completes.
        setTimeout(() => done(false), 5000);
      });
    }, padId);

    expect(wsOpened, 'Expected to open the collaboration WebSocket').toBe(true);
  });
});
