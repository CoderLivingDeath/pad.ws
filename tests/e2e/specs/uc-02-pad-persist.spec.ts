import { test, expect } from '@playwright/test';
import { keycloakLogin, createPadViaApi, setPadSharingPolicy } from './helpers';

test.describe('UC-02 pad create, edit, switch and persist', () => {
  test.beforeEach(async ({ page }) => {
    await keycloakLogin(page);
    await expect(page.locator('[data-testid="new-pad-button"]')).toBeVisible({ timeout: 10000 });
  });

  test('creates a pad from the UI and connects its collaboration WebSocket', async ({ page }) => {
    const before = await page.evaluate(async () => {
      const response = await fetch('/api/users/me');
      if (!response.ok) throw new Error(`Failed to fetch user profile: ${response.status}`);
      const data = await response.json();
      return data.pads.length as number;
    });

    await page.locator('[data-testid="new-pad-button"] button').first().click();
    await expect(page.locator('.active-pad [data-testid="tab-title"]')).toBeVisible({ timeout: 10000 });

    // Wait for the optimistic temp tab to be replaced by a real pad.
    await page.waitForFunction(
      async (countBefore: number) => {
        const response = await fetch('/api/users/me');
        const data = await response.json();
        return data.pads.length > countBefore;
      },
      before,
      { timeout: 10000 }
    );

    const padId = await page.evaluate(async () => {
      const response = await fetch('/api/users/me');
      const data = await response.json();
      return data.pads[data.pads.length - 1].id as string;
    });
    expect(padId).toBeTruthy();

    const wsOpened = await page.evaluate(
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
    expect(wsOpened, 'Expected to open the collaboration WebSocket').toBe(true);
  });

  test('saves a checkpoint before switching tabs and reload preserves the scene', async ({ page }) => {
    // Seed two pads through the API so we can focus on persistence.
    const firstPadId = await createPadViaApi(page, `Persist-${Date.now()}-A`);
    const secondPadId = await createPadViaApi(page, `Persist-${Date.now()}-B`);

    // Inject a minimal Excalidraw element into the first pad via the API.
    const seedElement = {
      id: `seed-${Date.now()}`,
      type: 'rectangle',
      x: 100,
      y: 100,
      width: 100,
      height: 100,
      angle: 0,
      strokeColor: '#000000',
      backgroundColor: 'transparent',
      fillStyle: 'hachure',
      strokeWidth: 1,
      strokeStyle: 'solid',
      roughness: 1,
      opacity: 100,
      groupIds: [],
      strokeSharpness: 'sharp',
      seed: 1,
      version: 1,
      versionNonce: 1,
      isDeleted: false,
      boundElementIds: null,
    };

    const putResponse = await page.request.put(`/api/pad/${firstPadId}/data`, {
      headers: { 'Content-Type': 'application/json' },
      data: { elements: [seedElement], files: {} },
    });
    expect(putResponse.ok(), `seed update failed: ${putResponse.status()}`).toBeTruthy();

    // Reload so the first pad is loaded from the backend.
    await page.goto('/');
    await expect(page.locator('[data-testid="new-pad-button"]')).toBeVisible({ timeout: 10000 });

    // Select the first pad.
    await page.locator(`[data-pad-id="${firstPadId}"]`).first().click();
    await expect(page.locator(`[data-pad-id="${firstPadId}"].active-pad`)).toBeVisible({ timeout: 10000 });

    // Switch to the second pad; this triggers saveCurrentPad() for the first pad.
    await page.locator(`[data-pad-id="${secondPadId}"]`).first().click();
    await expect(page.locator(`[data-pad-id="${secondPadId}"].active-pad`)).toBeVisible({ timeout: 10000 });

    // Switch back and verify the first pad still has the seeded element.
    await page.locator(`[data-pad-id="${firstPadId}"]`).first().click();
    await expect(page.locator(`[data-pad-id="${firstPadId}"].active-pad`)).toBeVisible({ timeout: 10000 });

    const afterSwitch = await page.evaluate(async (id) => {
      const response = await fetch(`/api/pad/${id}`);
      if (!response.ok) throw new Error(`Failed to fetch pad: ${response.status}`);
      const data = await response.json();
      return (data.elements || []).length as number;
    }, firstPadId);
    expect(afterSwitch).toBeGreaterThan(0);

    // Reload and verify persistence again.
    await page.reload();
    await expect(page.locator('[data-testid="new-pad-button"]')).toBeVisible({ timeout: 10000 });
    await page.locator(`[data-pad-id="${firstPadId}"]`).first().click();
    await expect(page.locator(`[data-pad-id="${firstPadId}"].active-pad`)).toBeVisible({ timeout: 10000 });

    const afterReload = await page.evaluate(async (id) => {
      const response = await fetch(`/api/pad/${id}`);
      if (!response.ok) throw new Error(`Failed to fetch pad: ${response.status}`);
      const data = await response.json();
      return (data.elements || []).length as number;
    }, firstPadId);
    expect(afterReload).toBeGreaterThan(0);
  });

  test('returns 404 for a missing pad', async ({ page }) => {
    const response = await page.request.get('/pad/00000000-0000-0000-0000-000000000000');
    expect(response.status()).toBe(404);
  });
});
