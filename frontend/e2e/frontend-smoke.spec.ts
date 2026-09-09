import { expect, test } from '@playwright/test';

const initResponse = {
  version: 'test',
  name: 'Blackbone CI',
  serial_no: 'test',
  serial_override: null,
  auth_required: true,
  pwa_name: 'Blackbone',
  pwa_default: 'Blackbone',
  pwa_max_length: 12,
  cloud: { enabled: false },
  has_boneio: true,
  board_version: '0.8',
  has_irrigation: false,
};

test('production frontend loads at / without runtime errors', async ({ page }) => {
  const runtimeErrors: string[] = [];
  const criticalResourceTypes = new Set(['document', 'script', 'stylesheet', 'image', 'font']);

  page.on('pageerror', error => runtimeErrors.push(`Uncaught exception: ${error.message}`));
  page.on('console', message => {
    if (message.type() === 'error') {
      runtimeErrors.push(`Console error: ${message.text()}`);
    }
  });
  page.on('requestfailed', request => {
    if (criticalResourceTypes.has(request.resourceType())) {
      runtimeErrors.push(`Failed ${request.resourceType()}: ${request.url()}`);
    }
  });
  page.on('response', response => {
    if (criticalResourceTypes.has(response.request().resourceType()) && response.status() >= 400) {
      runtimeErrors.push(`HTTP ${response.status()}: ${response.url()}`);
    }
  });

  await page.route('**/api/init', route => route.fulfill({ json: initResponse }));
  await page.route('**/api/config', route => route.fulfill({ json: {} }));
  await page.route('**/api/nodered/available', route => route.fulfill({ json: { available: false } }));
  await page.route('**/api/migrations/status', route => route.fulfill({
    json: {
      status: 'ok',
      bootstrap_required: false,
      helper_installed: true,
      pending_count: 0,
      pending: [],
      applied: [],
      last_error: null,
    },
  }));
  await page.route('**/nodered-status', route => route.fulfill({ json: { available: false } }));
  await page.route('**/manifest.webmanifest', route => route.fulfill({
    contentType: 'application/manifest+json',
    body: JSON.stringify({ name: 'Blackbone CI', start_url: '/', display: 'standalone' }),
  }));

  const response = await page.goto('/');

  expect(response?.ok()).toBe(true);
  await expect(page.locator('#root')).not.toBeEmpty();
  await expect(page.getByRole('heading', { name: /sign in to your boneio black/i })).toBeVisible();
  expect(runtimeErrors).toEqual([]);
});
