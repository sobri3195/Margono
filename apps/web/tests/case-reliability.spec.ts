import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';

const a = '8515b80b-9a75-4816-9315-24b96b4dad9c';
const b = '9515b80b-9a75-4816-9315-24b96b4dad9c';
const owner = '6f147ecb-f7d6-4c76-b402-afb637dc9630';
const fixture = {
  case_id: 'SYN-001', label: 'Synthetic test', workspace: 'web',
  scenario: 'Fixture', reference_id: 'SRC-FIXTURE', created_at: '2026-01-01T00:00:00Z',
};
const template = {
  owner_id: owner, synthetic_fixture_id: fixture.case_id, purpose: 'Synthetic operation',
  status: 'open', created_at: fixture.created_at, closed_at: null,
};

test.beforeEach(async ({ page }) => {
  await page.route('**/api/v1/simulation/catalog', (route) => route.fulfill({
    json: { mode: 'SYNTHETIC', cases: [fixture], sources: [], devices: [] },
  }));
  await page.route('**/api/v1/readiness', (route) => route.fulfill({
    status: 503,
    json: {
      mode: 'SYNTHETIC', status: 'not_ready', pilot: 'blocked',
      checks: { database: 'ready', worker: 'not_observed', sync: 'not_implemented' },
    },
  }));
  await page.route('**/api/v1/sessions', (route) => route.fulfill({
    status: 201, json: { token: 'synthetic-token', user_id: owner, roles: ['osint_analyst'] },
  }));
  await page.route('**/imports', (route) => route.fulfill({ json: { items: [], next_cursor: null } }));
});

test('recovers a committed case after reload and login with a read-only receipt lookup', async ({ page }) => {
  const keys: string[] = [];
  const closed = { ...template, id: a, status: 'closed', closed_at: '2026-01-01T01:00:00Z' };
  await page.route('**/api/v1/cases', (route) => {
    if (route.request().method() === 'GET') return route.fulfill({ json: [] });
    keys.push(route.request().headers()['idempotency-key']);
    if (keys.length === 1) return route.abort();
    return route.fulfill({ status: 201, json: { ...template, id: b } });
  });
  await page.route('**/api/v1/cases/creation-receipt', (route) => {
    expect(route.request().headers()['idempotency-key']).toBe(keys[0]);
    return route.fulfill({ json: closed });
  });
  await page.route(`**/api/v1/cases/${b}`, (route) => route.fulfill({ json: { ...template, id: b } }));
  await page.goto('/');

  async function login() {
    await page.getByLabel('Nama pengguna').fill('operator');
    await page.getByLabel('Kata sandi').fill('synthetic-password');
    await page.getByRole('button', { name: 'Masuk' }).click();
  }
  async function fillCase() {
    await page.getByLabel('Tujuan').fill('Synthetic test');
    await page.getByLabel('Ruang lingkup').fill('Fixture');
  }
  await login();
  await fillCase();
  await page.getByRole('button', { name: 'Buat kasus', exact: true }).click();
  await expect(page.getByRole('status').filter({ hasText: 'Kasus mungkin sudah tersimpan' })).toBeVisible();
  await page.reload();
  await login();
  await expect(page.getByLabel('Tujuan')).toHaveValue('');
  await expect(page.getByRole('button', { name: 'Buat kasus', exact: true })).toHaveCount(0);
  const check = page.getByRole('button', { name: 'Periksa hasil pembuatan' });
  await page.getByLabel('Ruang lingkup').focus();
  await page.keyboard.press('Tab');
  await expect(check).toBeFocused();
  await expect(check).toHaveAccessibleDescription(/Hasil pembuatan belum diketahui/);
  const accessibility = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze();
  expect(accessibility.violations).toEqual([]);
  await check.press('Enter');
  await expect(page.getByRole('status').filter({ hasText: 'Kasus ditemukan. Status saat ini ditutup.' })).toBeVisible();
  await expect(page.getByLabel('Kasus tersimpan')).toHaveValue(a);
  await expect(page.getByText('Ditutup', { exact: true })).toBeVisible();
  await expect(page.getByLabel('CSV sintetis')).toHaveCount(0);
  expect(keys).toHaveLength(1);
  await fillCase();
  await page.getByRole('button', { name: 'Buat kasus', exact: true }).click();
  await expect(page.getByLabel('Kasus tersimpan')).toHaveValue(b);
  expect(keys[1]).not.toBe(keys[0]);
});

test('retries a missing receipt with the same key and waits for the current case status', async ({ page }) => {
  const keys: string[] = [];
  await page.route('**/api/v1/cases', (route) => {
    if (route.request().method() === 'GET') return route.fulfill({ json: [] });
    keys.push(route.request().headers()['idempotency-key']);
    if (keys.length === 1) return route.abort();
    return route.fulfill({ status: 201, json: { ...template, id: a } });
  });
  await page.route('**/api/v1/cases/creation-receipt', (route) => route.fulfill({ json: null }));
  let release!: () => void;
  const waitForCase = new Promise<void>((resolve) => { release = resolve; });
  await page.route(`**/api/v1/cases/${a}`, async (route) => {
    await waitForCase;
    return route.fulfill({ json: { ...template, id: a, status: 'closed', closed_at: '2026-01-01T01:00:00Z' } });
  });
  await page.goto('/');
  await page.getByLabel('Nama pengguna').fill('operator');
  await page.getByLabel('Kata sandi').fill('synthetic-password');
  await page.getByRole('button', { name: 'Masuk' }).click();
  await page.getByLabel('Tujuan').fill('Synthetic test');
  await page.getByLabel('Ruang lingkup').fill('Fixture');
  await page.getByRole('button', { name: 'Buat kasus', exact: true }).click();
  const retry = page.getByRole('button', { name: 'Coba lagi pembuatan kasus' });
  await expect(retry).toBeEnabled();
  await page.getByRole('button', { name: 'Periksa hasil pembuatan' }).click();
  await expect(page.getByRole('status').filter({ hasText: 'Kasus belum ditemukan' })).toBeVisible();
  expect(keys).toHaveLength(1);
  await page.getByLabel('Ruang lingkup').fill('Other fixture');
  await retry.click();
  await expect(page.getByRole('alert')).toHaveText(/Isian berbeda/);
  expect(keys).toHaveLength(1);
  await page.getByLabel('Ruang lingkup').fill('Fixture');
  const started = page.waitForRequest(`**/api/v1/cases/${a}`);
  await retry.click();
  await started;
  await expect(page.getByLabel('CSV sintetis')).toHaveCount(0);
  release();
  await expect(page.getByText('Ditutup', { exact: true })).toBeVisible();
  await expect(page.getByLabel('CSV sintetis')).toHaveCount(0);
  expect(keys[0]).toBeTruthy();
  expect(keys).toEqual([keys[0], keys[0]]);
});

test('shows a confirmed request rejection without asking the operator to recover it', async ({ page }) => {
  await page.route('**/api/v1/cases', (route) => route.request().method() === 'POST'
    ? route.fulfill({ status: 422, json: { code: 'invalid_request' } })
    : route.fulfill({ json: [] }));
  await page.goto('/');
  await page.getByLabel('Nama pengguna').fill('operator');
  await page.getByLabel('Kata sandi').fill('synthetic-password');
  await page.getByRole('button', { name: 'Masuk' }).click();
  await page.getByLabel('Tujuan').fill('Synthetic test');
  await page.getByLabel('Ruang lingkup').fill('Fixture');
  const create = page.getByRole('button', { name: 'Buat kasus', exact: true });
  await create.click();
  await expect(page.getByRole('alert')).toHaveText('Periksa format dan isian formulir.');
  await expect(page.getByRole('button', { name: 'Periksa hasil pembuatan' })).toHaveCount(0);
  await expect(create).toBeEnabled();
});

test('older cases are reachable using the keyboard with the server cursor', async ({ page }) => {
  await page.route('**/api/v1/cases', (route) => route.fulfill({
    headers: { 'X-Next-Cursor': a }, json: [{ ...template, id: a }],
  }));
  await page.route(`**/api/v1/cases?before=${a}`, (route) => route.fulfill({
    json: [{ ...template, id: b, purpose: 'Older case' }],
  }));
  await page.goto('/');
  await page.getByLabel('Nama pengguna').fill('operator');
  await page.getByLabel('Kata sandi').fill('synthetic-password');
  await page.getByRole('button', { name: 'Masuk' }).click();
  const older = page.getByRole('button', { name: 'Muat kasus sebelumnya' });
  await older.focus();
  await older.press('Enter');
  const cases = page.getByRole('combobox', { name: 'Kasus tersimpan' });
  await expect(cases.getByRole('option', { name: /Older case/ })).toBeAttached();
  await expect(older).toHaveCount(0);
  await expect(cases).toHaveValue(a);
  await expect(cases).toBeFocused();
  const results = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze();
  expect(results.violations).toEqual([]);
});
