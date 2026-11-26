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
      checks: { database: 'ready', worker: 'not_observed', sync: 'not_implemented' },
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

test('reviews a source job and opens both reports from the same saved case', async ({ page }) => {
  const job = '6515b80b-9a75-4816-9315-24b96b4dad9c';
  const finding = '7515b80b-9a75-4816-9315-24b96b4dad9c';
  let queued = false;
  let verified = false;
  await page.route('**/imports', (route) => route.fulfill({
    json: { items: [summary], next_cursor: null },
  }));
  await page.route(`**/cases/${a}/imports/${batch}/details`, (route) => route.fulfill({
    json: {
      rows: [{ row_number: 2, reference_label: 'Label fixture', status: 'valid', duplicate: false }],
      events: [{ action: 'import.confirmed', occurred_at: timestamp, correlation_id: finding }],
    },
  }));
  function jobData() {
    return {
      id: job, case_id: a, import_id: batch, kind: 'synthetic_source',
      status: 'completed', attempts: 1, created_at: timestamp, failure_code: null, scheduled_at: null,
      review_pending: !verified, consent_active: false,
    };
  }
  function findingData() {
    return {
      id: finding, severity: 'low', threat_status: 'suspected',
      verification: verified ? 'verified' : 'pending',
      evidence_sha256: 'b'.repeat(64), review_note: verified ? 'Bukti dan batasan diperiksa' : null,
      evidence: {
        source_ref: 'SRC-FIXTURE', indicator: 'margono.test', observed_at: timestamp,
        limitation: 'Simulasi', import_id: batch, import_sha256: 'a'.repeat(64),
      },
    };
  }
  await page.route(`**/cases/${a}/imports/${batch}/jobs`, (route) => {
    expect(route.request().headers()['idempotency-key']).toBe(`source:${batch}`);
    queued = true;
    return route.fulfill({ status: 201, json: jobData() });
  });
  await page.route(`**/cases/${a}/jobs?*`, (route) => route.fulfill({
    headers: { 'X-Total-Count': queued ? '1' : '0' }, json: queued ? [jobData()] : [],
  }));
  await page.route(`**/cases/${a}/findings?*`, (route) => {
    const status = new URL(route.request().url()).searchParams.get('verification');
    const items = queued && status === findingData().verification ? [findingData()] : [];
    return route.fulfill({ headers: { 'X-Total-Count': String(items.length) }, json: items });
  });
  await page.route(`**/cases/${a}/collaborators`, (route) => route.fulfill({ json: [] }));
  await page.route(`**/cases/${a}/findings/${finding}/review`, (route) => {
    expect(route.request().postDataJSON()).toEqual({
      verification: 'verified', note: 'Bukti dan batasan diperiksa', expected: 'pending',
    });
    verified = true;
    return route.fulfill({ json: findingData() });
  });
  for (const template of ['executive', 'technical']) {
    await page.route(`**/cases/${a}/reports/${template}`, (route) => route.fulfill({
      json: { mode: 'SYNTHETIC', template, case_id: a },
    }));
  }

  await page.goto(`/?saved=${a}`);
  await page.getByLabel('Nama pengguna').fill('operator');
  await page.getByLabel('Kata sandi').fill('synthetic-password');
  await page.getByRole('button', { name: 'Masuk' }).click();
  await page.getByRole('button', { name: 'Periksa batch' }).click();
  await expect(page.getByText('Label fixture', { exact: false })).toBeVisible();
  await expect(page.getByText('import.confirmed', { exact: false })).toBeVisible();
  await page.getByRole('button', { name: 'Antrekan sumber sintetis' }).click();
  await page.getByRole('button', { name: 'Muat aktivitas kasus' }).click();
  await expect(page.getByText('margono.test', { exact: true })).toBeVisible();
  await page.getByLabel('Catatan relevansi dan batasan').fill('Bukti dan batasan diperiksa');
  await page.getByRole('button', { name: 'Simpan keputusan' }).click();
  await expect(page.getByText('0 dari 0 temuan')).toBeVisible();
  await page.getByLabel('Status review').selectOption('verified');
  await expect(page.getByText('Bukti dan batasan diperiksa')).toBeVisible();
  for (const name of ['Laporan eksekutif', 'Laporan teknis']) {
    await page.getByRole('button', { name }).click();
    await expect(page.getByRole('region', { name })).toContainText(a);
  }
});

test('restores a committed import from its exact confirmation after changing cases', async ({ page }) => {
  const nextBatch = '6515b80b-9a75-4816-9315-24b96b4dad9c';
  const keys: string[] = [];
  await page.route(`**/cases/${a}/imports`, (route) => {
    if (route.request().method() === 'POST') {
      keys.push(route.request().headers()['idempotency-key']);
      return keys.length === 1 ? route.abort() : route.fulfill({ status: 201, json: { ...summary, id: nextBatch } });
    }
    // Other imports can put the original batch beyond the first page.
    return route.fulfill({ json: { items: [], next_cursor: nextBatch } });
  });
  let otherLookups = 0;
  await page.route(`**/cases/${b}/imports/confirmation`, (route) => {
    otherLookups++;
    return route.fulfill({ json: null });
  });
  await page.route(`**/cases/${b}/imports`, (route) =>
    route.fulfill({ json: { items: [], next_cursor: null } }));
  await page.route(`**/cases/${a}/imports/confirmation`, (route) => {
    expect(route.request().headers()['idempotency-key']).toBe(keys[0]);
    return route.fulfill({ json: summary });
  });
  await page.route(`**/cases/${a}/imports/preview`, (route) => route.fulfill({
    json: { rows: [{ row_number: 2, reference_label: 'Fixture label', status: 'valid', duplicate: false }] },
  }));
  await page.goto(`/?saved=${a}`);
  await page.getByLabel('Nama pengguna').fill('operator');
  await page.getByLabel('Kata sandi').fill('synthetic-password');
  await page.getByRole('button', { name: 'Masuk' }).click();

  async function preview() {
    await page.getByLabel('CSV sintetis').setInputFiles({
      name: 'fixture.csv', mimeType: 'text/csv', buffer: Buffer.from('Unit,Label\nSatu,Fixture label\n'),
    });
    await page.getByLabel('Kolom label').selectOption('Label');
    await page.getByRole('button', { name: 'Pratinjau CSV' }).click();
    await page.getByRole('button', { name: 'Konfirmasi impor', exact: true }).click();
  }

  await preview();
  await expect(page.getByRole('button', { name: 'Coba lagi konfirmasi impor' })).toBeEnabled();
  const picker = page.getByRole('combobox', { name: 'Kasus tersimpan' });
  await picker.selectOption(b);
  await expect(page.getByText('Belum ada impor untuk kasus ini.')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Coba lagi konfirmasi impor' })).toHaveCount(0);
  expect(otherLookups).toBe(0);
  await picker.selectOption(a);
  await expect(page.getByRole('status').filter({ hasText: batch })).toBeVisible();
  expect(keys).toHaveLength(1);
  await preview();
  await expect(page.getByRole('status').filter({ hasText: nextBatch })).toBeVisible();
  expect(keys[1]).not.toBe(keys[0]);
});

test('resends an unconfirmed import with its original key only after the same preview', async ({ page }) => {
  const keys: string[] = [];
  await page.route(`**/cases/${a}/imports`, (route) => {
    if (route.request().method() !== 'POST') return route.fulfill({ json: { items: [], next_cursor: null } });
    keys.push(route.request().headers()['idempotency-key']);
    return keys.length === 1 ? route.abort() : route.fulfill({ status: 201, json: summary });
  });
  await page.route(`**/cases/${b}/imports`, (route) =>
    route.fulfill({ json: { items: [], next_cursor: null } }));
  await page.route(`**/cases/${a}/imports/confirmation`, (route) => route.fulfill({ json: null }));
  await page.route(`**/cases/${a}/imports/preview`, (route) => route.fulfill({
    json: { rows: [{ row_number: 2, reference_label: 'Fixture label', status: 'valid', duplicate: false }] },
  }));
  await page.goto(`/?saved=${a}`);
  await page.getByLabel('Nama pengguna').fill('operator');
  await page.getByLabel('Kata sandi').fill('synthetic-password');
  await page.getByRole('button', { name: 'Masuk' }).click();

  async function preview(label: string) {
    await page.getByLabel('Label manual, satu per baris').fill(label);
    await page.getByRole('button', { name: 'Pratinjau label manual' }).click();
    await expect(page.getByRole('list', { name: 'Pratinjau baris impor' })).toBeVisible();
  }
  await preview('Fixture label');
  await page.getByRole('button', { name: 'Konfirmasi impor', exact: true }).click();
  await expect(page.getByRole('status').filter({ hasText: 'Batch mungkin sudah tersimpan' })).toBeVisible();
  const check = page.getByRole('button', { name: 'Periksa riwayat konfirmasi' });
  await check.focus();
  await expect(check).toHaveAccessibleDescription(/Hasil konfirmasi belum diketahui/);
  await check.press('Enter');
  await expect(page.getByRole('status').filter({ hasText: 'Hasil konfirmasi belum ditemukan di riwayat' })).toBeVisible();
  expect(keys).toHaveLength(1);
  const picker = page.getByRole('combobox', { name: 'Kasus tersimpan' });
  await picker.selectOption(b);
  await picker.selectOption(a);
  const retry = page.getByRole('button', { name: 'Coba lagi konfirmasi impor' });
  await preview('Other label');
  await retry.click();
  await expect(page.getByRole('alert')).toContainText('Impor berbeda dari konfirmasi sebelumnya');
  expect(keys).toHaveLength(1);
  await preview('Fixture label');
  await retry.click();
  await expect(page.getByRole('status').filter({ hasText: batch })).toBeVisible();
  expect(keys[0]).toBeTruthy();
  expect(keys).toEqual([keys[0], keys[0]]);
});
