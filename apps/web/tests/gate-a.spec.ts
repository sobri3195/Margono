import { expect, test, type Page } from '@playwright/test';

const timestamp = '2026-01-01T00:00:00Z';
const owner = '2b7f4ad2-344a-4b0e-8419-a78d3fd03c91';
const webCase = '3515b80b-9a75-4816-9315-24b96b4dad9c';
const usbCase = '4515b80b-9a75-4816-9315-24b96b4dad9c';
const sessionId = '5515b80b-9a75-4816-9315-24b96b4dad9c';
const jobId = '6515b80b-9a75-4816-9315-24b96b4dad9c';
const otherJob = '7515b80b-9a75-4816-9315-24b96b4dad9c';
const fixture = {
  label: 'Fixture sintetis', scenario: 'Fixture', created_at: timestamp,
};
const cases = [
  { id: webCase, owner_id: owner, synthetic_fixture_id: 'SYN-001', purpose: 'Web', status: 'open', created_at: timestamp, closed_at: null },
  { id: usbCase, owner_id: owner, synthetic_fixture_id: 'SYN-011', purpose: 'USB', status: 'open', created_at: timestamp, closed_at: null },
];
const job = {
  id: jobId, case_id: webCase, kind: 'synthetic_source', status: 'failed', attempts: 1,
  created_at: timestamp, failure_code: 'case_closed', scheduled_at: null, review_pending: false, consent_active: false,
};

async function login(page: Page, role: string, saved?: string) {
  await page.route('**/api/v1/sessions', (route) => route.fulfill({
    status: 201, json: { token: 'fixture-session', user_id: owner, roles: [role] },
  }));
  await page.goto(saved ? `/?saved=${saved}` : '/');
  await page.getByLabel('Nama pengguna').fill('operator');
  await page.getByLabel('Kata sandi').fill('fixture-password');
  await page.getByRole('button', { name: 'Masuk', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Keluar' })).toBeVisible();
}

test.beforeEach(async ({ page }) => {
  await page.route('**/api/v1/simulation/catalog', (route) => route.fulfill({ json: {
    mode: 'SYNTHETIC', devices: [], sources: [], cases: [
      { ...fixture, case_id: 'SYN-001', workspace: 'web', reference_id: 'SRC-FIXTURE' },
      { ...fixture, case_id: 'SYN-011', workspace: 'usb', reference_id: 'DEV-ANDROID' },
    ],
  } }));
  await page.route('**/api/v1/readiness', (route) => route.fulfill({ status: 503, json: {
    mode: 'SYNTHETIC', status: 'not_ready', pilot: 'blocked',
    checks: { database: 'ready', worker: 'active', sync: 'not_implemented' },
  } }));
  await page.route('**/api/v1/cases', (route) => route.fulfill({ json: cases }));
  await page.route('**/imports', (route) => route.fulfill({ json: { items: [], next_cursor: null } }));
  await page.route('**/collaborators', (route) => route.fulfill({ json: [] }));
});

test('recovers the original consent decision after a lost response, switching cases and reloading', async ({ page }) => {
  const keys: string[] = [];
  const saved = {
    id: sessionId, status: 'granted', decided_at: timestamp, revoked_at: null,
    job_id: null, evidence: null, evidence_sha256: null,
  };
  await page.route(`**/cases/${usbCase}/devices`, (route) => {
    if (route.request().method() === 'POST') {
      keys.push(route.request().headers()['idempotency-key']);
      return keys.length === 1
        ? route.abort()
        : route.fulfill({ status: 201, json: { ...saved, status: 'declined' } });
    }
    return route.fulfill({ json: {
      mode: 'SYNTHETIC', platform: 'android', scope: 'Fixture', disclosure: 'Simulasi',
      sessions: keys.length ? [saved] : [],
    } });
  });
  await page.route(`**/cases/${usbCase}/devices/decision`, (route) => {
    expect(route.request().headers()['idempotency-key']).toBe(keys[0]);
    return route.fulfill({ json: saved });
  });
  await login(page, 'forensic_examiner', usbCase);
  await page.getByRole('button', { name: 'Muat sesi perangkat' }).click();
  await page.getByRole('button', { name: 'Catat persetujuan simulasi' }).click();
  const dialog = page.getByRole('dialog');
  await dialog.getByRole('button', { name: 'Catat persetujuan', exact: true }).click();
  await expect(dialog.getByRole('alert')).toBeVisible();
  await expect(dialog.getByRole('button', { name: 'Catat persetujuan', exact: true })).toHaveCount(0);
  await dialog.getByRole('button', { name: 'Tutup dialog' }).click();
  const picker = page.getByLabel('Kasus tersimpan');
  await picker.selectOption(webCase);
  await expect(page.getByRole('button', { name: 'Periksa keputusan' })).toHaveCount(0);
  await picker.selectOption(usbCase);
  await page.reload();
  await page.getByLabel('Nama pengguna').fill('operator');
  await page.getByLabel('Kata sandi').fill('fixture-password');
  await page.getByRole('button', { name: 'Masuk', exact: true }).click();

  await page.getByRole('button', { name: 'Periksa keputusan' }).click();
  await expect(page.getByRole('status').filter({ hasText: sessionId })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Periksa keputusan' })).toHaveCount(0);
  expect(keys).toHaveLength(1);
  await page.getByRole('button', { name: 'Catat persetujuan simulasi' }).click();
  await dialog.getByRole('button', { name: 'Catat penolakan' }).click();
  await expect(dialog).toHaveCount(0);
  expect(keys).toHaveLength(2);
  expect(keys[1]).not.toBe(keys[0]);
});

test('shows scoped portal counters and opens a job case without losing the operator session', async ({ page }) => {
  await page.route('**/api/v1/jobs', (route) => route.fulfill({
    headers: { 'X-Total-Count': '101', 'X-Failed-Count': '2', 'X-Pending-Review-Count': '99' },
    json: [{ ...job, case_id: usbCase }],
  }));
  await page.route(`**/api/v1/cases/${usbCase}`, (route) => route.fulfill({ json: cases[1] }));
  await login(page, 'osint_analyst', webCase);
  const portal = page.getByRole('region', { name: 'Pekerjaan portal' });
  await portal.getByRole('button', { name: 'Muat pekerjaan portal' }).click();
  await expect(portal.getByRole('status')).toContainText('2 pekerjaan gagal');
  await expect(portal.getByRole('status')).toContainText('99 temuan menunggu review');
  await expect(portal.getByRole('status')).toContainText('Menampilkan 1 dari 101 pekerjaan');
  await portal.getByRole('link', { name: 'Buka kasus' }).press('Enter');
  await expect(page.getByLabel('Kasus tersimpan')).toHaveValue(usbCase);
  await expect(page.getByRole('button', { name: 'Keluar' })).toBeVisible();
  await expect(page).toHaveURL(new RegExp(`saved=${usbCase}`));
});

test('leaves the portal jobs panel hidden for administrators without a case role', async ({ page }) => {
  await login(page, 'administrator');
  await expect(page.getByRole('region', { name: 'Pekerjaan portal' })).toHaveCount(0);
});

test('pages both activity lists and submits a finding on the next pending page', async ({ page }) => {
  const first = { id: jobId, verification: 'pending', severity: 'low', threat_status: 'suspected', evidence_sha256: 'a'.repeat(64),
    review_note: null, reviewed_by: null, reviewed_at: null, evidence: {
      source_ref: 'SRC-FIXTURE', observed_at: timestamp, indicator: 'fixture-1.test', limitation: 'Sintetis',
      import_id: sessionId, import_sha256: 'b'.repeat(64),
    },
  };
  const second = { ...first, id: otherJob, evidence: { ...first.evidence, indicator: 'fixture-2.test' } };
  const verified = { ...second, verification: 'verified', reviewed_by: owner, reviewed_at: timestamp };
  let reviewed = false;
  await page.route(`**/cases/${webCase}/jobs?*`, (route) => {
    const before = new URL(route.request().url()).searchParams.get('before');
    return route.fulfill(before ? {
      headers: { 'X-Total-Count': '2' }, json: [{ ...job, id: otherJob }],
    } : {
      headers: { 'X-Total-Count': '2', 'X-Next-Cursor': jobId }, json: [job],
    });
  });
  await page.route(`**/cases/${webCase}/findings?*`, (route) => {
    const query = new URL(route.request().url()).searchParams;
    if (query.get('verification') === 'verified') {
      return route.fulfill({ headers: { 'X-Total-Count': '1' }, json: [verified] });
    }
    expect(query.get('verification')).toBe('pending');
    if (query.get('after') === jobId) {
      return route.fulfill({ headers: { 'X-Total-Count': '2' }, json: [second] });
    }
    return route.fulfill({
      headers: reviewed ? { 'X-Total-Count': '1' } : { 'X-Total-Count': '2', 'X-Next-Cursor': jobId }, json: [first],
    });
  });
  await page.route(`**/findings/${otherJob}/review`, (route) => {
    expect(route.request().postDataJSON()).toEqual({ verification: 'verified', note: 'Fixture terverifikasi', expected: 'pending' });
    reviewed = true;
    return route.fulfill({ json: verified });
  });
  await login(page, 'osint_analyst', webCase);
  await page.getByRole('button', { name: 'Muat aktivitas kasus' }).click();
  await expect(page.getByText('1 dari 2 pekerjaan')).toBeVisible();
  await expect(page.getByText('1 dari 2 temuan')).toBeVisible();
  await page.getByRole('button', { name: 'Muat pekerjaan berikutnya' }).click();
  await expect(page.getByText('2 dari 2 pekerjaan')).toBeVisible();
  await page.getByRole('button', { name: 'Muat temuan berikutnya' }).click();
  await expect(page.getByText('2 dari 2 temuan')).toBeVisible();
  const finding = page.getByRole('listitem').filter({ hasText: 'fixture-2.test' });
  await finding.getByLabel('Catatan relevansi dan batasan').fill('Fixture terverifikasi');
  await finding.getByRole('button', { name: 'Simpan keputusan' }).click();
  await expect(page.getByText('1 dari 1 temuan')).toBeVisible();
  await expect(finding).toHaveCount(0);
  await page.getByLabel('Status review').selectOption('verified');
  await expect(finding).toContainText('Terverifikasi');
  await expect(finding.getByRole('button', { name: 'Simpan keputusan' })).toHaveCount(0);
});

test('offers a failed mock scan retry only while consent is active', async ({ page }) => {
  let retried = false;
  await page.route(`**/cases/${usbCase}/jobs?*`, (route) => route.fulfill({
    headers: { 'X-Total-Count': '2' }, json: [
      { ...job, kind: 'synthetic_device', case_id: usbCase, consent_active: true, status: retried ? 'queued' : 'failed' },
      { ...job, id: otherJob, kind: 'synthetic_device', case_id: usbCase, consent_active: false },
    ],
  }));
  await page.route(`**/cases/${usbCase}/findings?*`, (route) => route.fulfill({
    headers: { 'X-Total-Count': '0' }, json: [],
  }));
  await page.route(`**/cases/${usbCase}/jobs/${jobId}?action=retry`, (route) => {
    expect(route.request().method()).toBe('PATCH');
    retried = true;
    return route.fulfill({ json: { id: jobId, status: 'queued' } });
  });
  await login(page, 'forensic_examiner', usbCase);
  await page.getByRole('button', { name: 'Muat aktivitas kasus' }).click();
  const retry = page.getByRole('button', { name: 'Ulangi mock scan' });
  await expect(retry).toHaveCount(1);
  await retry.click();
  await expect(retry).toHaveCount(0);
  expect(retried).toBe(true);
});

test('keeps web-case jobs available to a forensic collaborator without requesting technical findings', async ({ page }) => {
  let findingsRequested = false;
  await page.route(`**/cases/${webCase}/findings?*`, (route) => {
    findingsRequested = true;
    return route.fulfill({ status: 403, json: {} });
  });
  await page.route(`**/cases/${webCase}/jobs?*`, (route) => route.fulfill({
    headers: { 'X-Total-Count': '1' }, json: [job],
  }));
  await login(page, 'forensic_examiner', webCase);
  await page.getByRole('button', { name: 'Muat aktivitas kasus' }).click();
  await expect(page.getByText('1 dari 1 pekerjaan')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Review temuan sintetis' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Laporan teknis' })).toHaveCount(0);
  expect(findingsRequested).toBe(false);
});

test('lets a supervisor inspect the actor and correlation ID for a revoked consent', async ({ page }) => {
  await page.route(`**/cases/${usbCase}/devices`, (route) => route.fulfill({ json: {
    mode: 'SYNTHETIC', platform: 'android', scope: 'Fixture', disclosure: 'Simulasi',
    sessions: [{
      id: sessionId, status: 'revoked', decided_at: timestamp, revoked_at: timestamp,
      job_id: null, evidence: null, evidence_sha256: null,
    }],
  } }));
  await page.route(`**/cases/${usbCase}/devices/${sessionId}/audit`, (route) => route.fulfill({ json: [{
    id: jobId, action: 'device.consent.revoked', actor_id: owner,
    occurred_at: timestamp, correlation_id: otherJob,
  }] }));
  await login(page, 'supervisor', usbCase);
  await page.getByRole('button', { name: 'Muat sesi perangkat' }).click();
  await page.getByRole('button', { name: 'Periksa audit sesi' }).click();
  const audit = page.getByRole('region', { name: 'Audit sesi perangkat' });
  await expect(audit).toContainText(sessionId);
  await expect(audit).toContainText(`Aktor ${owner}`);
  await expect(audit).toContainText(`ID korelasi ${otherJob}`);
});
