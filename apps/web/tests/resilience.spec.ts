import { expect, test } from '@playwright/test';

const catalogUrl = '**/api/v1/simulation/catalog';
const correlationId = '3e75e05f-7121-4d8c-8350-9d791fb5a8bb';
const headers = { 'X-Correlation-ID': correlationId };
const catalog = {
  mode: 'SYNTHETIC',
  sources: [],
  devices: [],
  cases: [{ case_id: 'SYN-001', label: 'Kasus contoh', workspace: 'web', scenario: 'Fixture', reference_id: 'SRC-FIXTURE', created_at: '2026-01-01T00:00:00Z' }],
};

test.beforeEach(async ({ page }) => {
  await page.route('**/api/v1/readiness', (route) => route.fulfill({
    status: 503,
    json: {
      mode: 'SYNTHETIC',
      status: 'not_ready',
      pilot: 'blocked',
      checks: { database: 'migration_required', worker: 'not_observed', sync: 'not_implemented' },
    },
  }));
});

test('rejects malformed catalog and presents a correlated retry', async ({ page }) => {
  await page.route(catalogUrl, (route) => route.fulfill({ headers, json: { mode: 'SYNTHETIC', cases: null } }));
  await page.goto('/');
  await expect(page.getByRole('alert')).toHaveText('Respons katalog tidak valid.');
  await expect(page.getByText(correlationId)).toBeVisible();
  await expect(page.getByText('Memerlukan migrasi')).toBeVisible();
  await page.unroute(catalogUrl);
  await page.route(catalogUrl, (route) => route.fulfill({ json: catalog }));
  await page.getByRole('button', { name: 'Coba lagi' }).click();
  await expect(page.getByRole('heading', { name: 'Kasus contoh' })).toBeVisible();
  await expect(page.getByText('Belum siap')).toBeVisible();
});

test('aborts a stalled request at the deadline and allows another attempt', async ({ page }) => {
  await page.clock.install();
  let observedRequest!: () => void;
  const requestStarted = new Promise<void>((resolve) => { observedRequest = resolve; });
  await page.route(catalogUrl, () => { observedRequest(); });
  await page.goto('/');
  await requestStarted;
  await expect(page.getByText('Memuat katalog…')).toBeVisible();
  await page.clock.fastForward(10_001);
  await expect(page.getByRole('alert')).toHaveText('Permintaan katalog melewati batas waktu.');
  await page.unroute(catalogUrl);
  await page.route(catalogUrl, (route) => route.fulfill({ json: catalog }));
  await page.getByRole('button', { name: 'Coba lagi' }).click();
  await expect(page.getByRole('heading', { name: 'Kasus contoh' })).toBeVisible();
});

test('keeps the page usable when catalog rendering throws and resets the boundary on retry', async ({ page }) => {
  await page.addInitScript(() => {
    const originalFilter = Array.prototype.filter;
    Array.prototype.filter = function (callback, thisArg) {
      if (this[0]?.case_id === 'SYN-FAIL') throw new Error('Synthetic render failure');
      return originalFilter.call(this, callback, thisArg);
    };
  });
  await page.route(catalogUrl, (route) => route.fulfill({
    headers,
    json: { ...catalog, cases: [{ ...catalog.cases[0], case_id: 'SYN-FAIL' }] },
  }));
  await page.goto('/');
  await expect(page.getByRole('alert')).toHaveText('Katalog tidak dapat ditampilkan.');
  await expect(page.getByText(correlationId)).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Status operasional' })).toBeVisible();
  await page.unroute(catalogUrl);
  await page.route(catalogUrl, (route) => route.fulfill({ json: catalog }));
  await page.getByRole('button', { name: 'Coba lagi' }).click();
  await expect(page.getByRole('heading', { name: 'Kasus contoh' })).toBeVisible();
});

test('shows an HTTP failure correlation ID while keeping readiness independent', async ({ page }) => {
  await page.route(catalogUrl, (route) => route.fulfill({ status: 503, headers, json: {} }));
  await page.goto('/');
  await expect(page.getByRole('alert')).toContainText('Katalog tidak dapat dimuat.');
  await expect(page.getByText(correlationId)).toBeVisible();
  await expect(page.getByText('Memerlukan migrasi')).toBeVisible();
});
