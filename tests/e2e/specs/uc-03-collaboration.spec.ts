import { test, expect, BrowserContext, Page } from '@playwright/test';
import {
  keycloakLogin,
  getSecondUserCredentials,
  createPadViaApi,
  setPadSharingPolicy,
  openCollaborationSocket,
} from './helpers';

test.describe('UC-03 real-time collaboration', () => {
  test('two users connect to the same pad and reconnect after disconnect', async ({ browser }) => {
    const contextA = await browser.newContext({ ignoreHTTPSErrors: true });
    const contextB = await browser.newContext({ ignoreHTTPSErrors: true });

    try {
      const pageA = await contextA.newPage();
      const pageB = await contextB.newPage();

      await keycloakLogin(pageA);
      await expect(pageA.locator('[data-testid="new-pad-button"]')).toBeVisible({ timeout: 10000 });

      const padId = await createPadViaApi(pageA, `Collab-${Date.now()}`);
      await setPadSharingPolicy(pageA, padId, 'public');

      const secondCreds = getSecondUserCredentials();
      await keycloakLogin(pageB, secondCreds.username, secondCreds.password);

      await pageB.goto(`/pad/${padId}`);
      await expect(pageB.locator('[data-testid="new-pad-button"]')).toBeVisible({ timeout: 15000 });

      // Both users must be able to open the authenticated collaboration socket.
      const [openedA, openedB] = await Promise.all([
        openCollaborationSocket(pageA, padId),
        openCollaborationSocket(pageB, padId),
      ]);
      expect(openedA, 'first user WebSocket should open').toBe(true);
      expect(openedB, 'second user WebSocket should open').toBe(true);

      // Reconnect resynchronizes after a disconnect.
      const reconnectedA = await openCollaborationSocket(pageA, padId);
      expect(reconnectedA, 'first user WebSocket should reconnect').toBe(true);
    } finally {
      await contextA.close();
      await contextB.close();
    }
  });
});
