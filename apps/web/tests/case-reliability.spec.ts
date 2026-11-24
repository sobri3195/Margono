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
      checks: { database: 'ready', worker: 'not_implemented', sync: 'not_implemented' },
    },
  }));
  await page.route('**/api/v1/sessions', (route) => route.fulfill({
    status: 201, json: { token: 'synthetic-token', user_id: owner, roles: ['osint_analyst'] },
  }));
  await page.route('**/imports', (route) => route.fulfill({ json: { items: [], next_cursor: null } }));
});

test('retries a lost case response with the same key and gives the next creation a new key', async ({ page }) => {
  const keys: string[] = [];
  await page.route('**/api/v1/cases', (route) => {
    if (route.request().method() === 'GET') return route.fulfill({ json: [] });
    keys.push(route.request().headers()['idempotency-key']);
    if (keys.length === 1) return route.abort();
    return route.fulfill({ status: 201, json: { ...template, id: keys.length === 2 ? a : b } });
  });
  await page.goto('/');
  await page.getByLabel('Nama pengguna').fill('operator');
  await page.getByLabel('Kata sandi').fill('synthetic-password');
  await page.getByRole('button', { name: 'Masuk' }).click();
  const create = page.getByRole('button', { name: 'Buat kasus' });
  await page.getByLabel('Tujuan').fill('Synthetic test');
  await page.getByLabel('Ruang lingkup').fill('Fixture');
  await create.click();
  await expect(page.getByRole('alert')).toHaveText('Operasi gagal. Coba lagi.');
  await create.click();
  await expect(page.getByLabel('Kasus tersimpan')).toHaveValue(a);
  expect(keys[0]).toBeTruthy();
  expect(keys[0]).toBe(keys[1]);
  await page.getByLabel('Tujuan').fill('Synthetic test');
  await page.getByLabel('Ruang lingkup').fill('Fixture');
  await create.click();
  await expect(page.getByLabel('Kasus tersimpan')).toHaveValue(b);
  expect(keys[2]).not.toBe(keys[1]);
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
