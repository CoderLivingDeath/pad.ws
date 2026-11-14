import { test, expect } from '@playwright/test';
import { keycloakLogin, getTestCredentials, getBaseUrls, fetchWorkspaceState } from './helpers';

test.describe('UC-04 Coder workspace and terminal', () => {
  test.beforeEach(async ({ page }) => {
    await keycloakLogin(page);
  });

  test('workspace state endpoint reports the user workspace', async ({ page }) => {
    const state = await fetchWorkspaceState(page);
    expect(state).toHaveProperty('state');
    expect(state).toHaveProperty('username');
    expect(['pending', 'starting', 'running', 'stopping', 'stopped', 'failed', 'canceling', 'canceled', 'deleting', 'deleted']).toContain(state.state);
  });

  test('starting a workspace without a provisioned workspace returns 409', async ({ page }) => {
    const state = await fetchWorkspaceState(page);
    if (state.id) {
      test.info().annotations.push({
        type: 'prerequisite',
        description: 'A workspace is already provisioned; the no-workspace 409 path is covered when no template is available.',
      });
      return;
    }

    const response = await page.request.post('/api/workspace/start', {
      headers: { Accept: 'application/json' },
    });
    expect(response.status()).toBe(409);
  });

  test('embedded terminal iframe loads for a running workspace', async ({ page }) => {
    const state = await fetchWorkspaceState(page);
    const urls = getBaseUrls();
    const creds = getTestCredentials();

    if (state.state !== 'running' || !state.name || !state.username) {
      throw new Error(
        'Workspace is not running. Full terminal verification requires a provisioned Coder template and a running workspace (staging gate).'
      );
    }

    const terminalUrl = `${urls.coder}/@${state.username}/${state.name}.${state.agent}/terminal`;
    await page.goto(terminalUrl);
    await page.waitForLoadState('networkidle');

    await expect(page.locator('[data-testid="terminal-iframe"], iframe[title*="terminal" i]')).toBeVisible({
      timeout: 30000,
    });
  });
});
