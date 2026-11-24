import { expect, test } from '@playwright/test';

const owner = '2b7f4ad2-344a-4b0e-8419-a78d3fd03c91';
const a = '3515b80b-9a75-4816-9315-24b96b4dad9c';
const b = '4515b80b-9a75-4816-9315-24b96b4dad9c';
const batch = '5515b80b-9a75-4816-9315-24b96b4dad9c';
const timestamp = '2026-01-01T00:00:00Z';
const fixture = {
  case_id: 'SYN-001', label: 'Synthetic fixture', workspace: 'web',
  scenario: 'Fixture', reference_id: 'SRC-FIXTURE', created_at: timestamp,
};
const summary = {
  id: batch, created_at: timestamp, sha256: 'a'.repeat(64),
  selected_column: 'Label', row_count: 2, valid_count: 1, invalid_count: 1,
};

test.beforeEach(async ({ page }) => {
  await page.route('**/api/v1/simulation/catalog', (route) => route.fulfill({
    json: { mode: 'SYNTHETIC', sources: [], devices: [], cases: [fixture] },
  }));
  await page.route('**/api/v1/readiness', (route) => route.fulfill({
    status: 503,
    json: {
      mode: 'SYNTHETIC', status: 'not_ready', pilot: 'blocked',
      checks: { database: 'ready', worker: 'not_implemented', sync: 'not_implemented' },
    },
  }));
  await page.route('**/api/v1/sessions', (route) => route.fulfill({
    status: 201, json: { token: 'synthetic', user_id: owner, roles: ['osint_analyst'] },
  }));
  await page.route('**/api/v1/cases', (route) => route.fulfill({
    json: [a, b].map((id, index) => ({
      id, owner_id: owner, synthetic_fixture_id: fixture.case_id, purpose: `Kasus ${index + 1}`,
      status: 'open', created_at: timestamp, closed_at: null,
    })),
  }));
  await page.route('**/imports/columns', (route) => route.fulfill({ json: { columns: ['Unit', 'Label'] } }));
});

test('Back ignores a late preview from the previous case even when fetch does not abort', async ({ page }) => {
  await page.addInitScript(() => {
    // Simulate a response arriving after cancellation.
    const original = window.fetch;
    window.fetch = (input, options) =>
      original(input, typeof input === 'string' && input.endsWith('/imports/preview')
        ? { ...options, signal: undefined }
        : options);
  });
  await page.route('**/imports', (route) => route.fulfill({ json: { items: [], next_cursor: null } }));
  let release!: () => void;
  const delay = new Promise<void>((resolve) => { release = resolve; });
  await page.route(`**/cases/${b}/imports/preview`, async (route) => {
    await delay;
    await route.fulfill({ json: { rows: [
      { row_number: 2, reference_label: 'Baris untuk B', status: 'valid', duplicate: false },
    ] } });
  });
  await page.goto(`/?saved=${a}`);
  await page.getByLabel('Nama pengguna').fill('operator');
  await page.getByLabel('Kata sandi').fill('synthetic-password');
  await page.getByRole('button', { name: 'Masuk' }).click();
  const picker = page.getByRole('combobox', { name: 'Kasus tersimpan' });
  await expect(picker).toHaveValue(a);
  await picker.selectOption(b);
  await page.getByLabel('CSV sintetis').setInputFiles({
    name: 'fixture.csv', mimeType: 'text/csv', buffer: Buffer.from('Unit,Label\nFixture,B\n'),
  });
  const started = page.waitForRequest(`**/cases/${b}/imports/preview`);
  await page.getByRole('button', { name: 'Pratinjau CSV' }).click();
  await started;
  await page.goBack();
  await expect(picker).toHaveValue(a);
  const arrived = page.waitForResponse(`**/cases/${b}/imports/preview`);
  release();
  await (await arrived).finished();
  await page.evaluate(() => new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))));
  await expect(page.getByText('Baris untuk B')).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Konfirmasi impor' })).toHaveCount(0);
  await page.goForward();
  await expect(picker).toHaveValue(b);
  await expect(page.getByRole('button', { name: 'Konfirmasi impor' })).toHaveCount(0);
});

test('selects a CSV header, confirms the same case, and reopens saved history', async ({ page }) => {
  let saved = false;
  await page.route(`**/cases/${a}/imports`, (route) => {
    if (route.request().method() === 'POST') {
      expect(route.request().postDataJSON().column).toBe('Label');
      expect(route.request().headers()['idempotency-key']).toBeTruthy();
      saved = true;
      return route.fulfill({ status: 201, json: summary });
    }
    return route.fulfill({ json: { items: saved ? [summary] : [], next_cursor: null } });
  });
  await page.route(`**/cases/${a}/imports/preview`, (route) => route.fulfill({
    json: { rows: [
      { row_number: 2, reference_label: 'Fixture', status: 'valid', duplicate: false },
      { row_number: 3, reference_label: null, status: 'invalid', duplicate: false },
    ] },
  }));
  await page.route(`**/cases/${b}/imports`, (route) =>
    route.fulfill({ json: { items: [], next_cursor: null } }));
  await page.goto(`/?saved=${a}`);
  await page.getByLabel('Nama pengguna').fill('operator');
  await page.getByLabel('Kata sandi').fill('synthetic-password');
  await page.getByRole('button', { name: 'Masuk' }).click();
  await page.getByLabel('CSV sintetis').setInputFiles({
    name: 'fixture.csv', mimeType: 'text/csv', buffer: Buffer.from('Unit,Label\nSatu,Fixture\nDua,\n'),
  });
  await page.getByRole('combobox', { name: 'Kolom label' }).selectOption('Label');
  await page.getByRole('button', { name: 'Pratinjau CSV' }).click();
  await page.getByRole('button', { name: 'Konfirmasi impor' }).click();
  await expect(page.getByText('2 baris tersimpan. 1 valid, 1 tidak valid.')).toBeVisible();
  const history = page.getByRole('list', { name: 'Riwayat impor kasus' });
  await expect(history.getByText('Kolom Label', { exact: false })).toBeVisible();
  await expect(history.getByRole('button', { name: 'Unduh bukti' })).toBeVisible();
  const picker = page.getByRole('combobox', { name: 'Kasus tersimpan' });
  await picker.selectOption(b);
  await expect(page.getByText('Belum ada impor untuk kasus ini.')).toBeVisible();
  await picker.selectOption(a);
  await expect(history.getByText('Kolom Label', { exact: false })).toBeVisible();
});

test('returns to sign-in when import history reports an expired session', async ({ page }) => {
  const correlationId = '9515b80b-9a75-4816-9315-24b96b4dad9c';
  await page.route(`**/cases/${a}/imports`, (route) => route.fulfill({
    status: 401, headers: { 'X-Correlation-ID': correlationId }, json: {},
  }));
  await page.goto(`/?saved=${a}`);
  await page.getByLabel('Nama pengguna').fill('operator');
  await page.getByLabel('Kata sandi').fill('synthetic-password');
  await page.getByRole('button', { name: 'Masuk' }).click();
  await expect(page.getByRole('alert')).toHaveText('Sesi telah berakhir. Silakan masuk kembali.');
  await expect(page.getByText(correlationId)).toBeVisible();
  await expect(page.getByRole('button', { name: 'Masuk' })).toBeVisible();
});
