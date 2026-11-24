import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';

const timestamp = '2026-01-01T00:00:00Z';
const correlation = '5515b80b-9a75-4816-9315-24b96b4dad9c';
const savedId = 'dc7bb719-ee17-41e9-8474-30bd33d003f5';
const ownerId = 'eb0a0e5f-d595-4fda-be3a-81711f33a4e2';
const anotherCase = {
  id: '2b7f4ad2-344a-4b0e-8419-a78d3fd03c91', owner_id: ownerId, synthetic_fixture_id: 'SYN-002',
  purpose: 'Kasus lain', status: 'open', created_at: timestamp, closed_at: null,
};
const catalog = {
  mode: 'SYNTHETIC',
  sources: [],
  devices: [],
  cases: [
    ['SYN-001', 'Web pertama', 'web'],
    ['SYN-002', 'Web kedua', 'web'],
    ['SYN-011', 'USB pertama', 'usb'],
    ['SYN-012', 'USB kedua', 'usb'],
  ].map(([case_id, label, workspace]) => ({
    case_id, label, workspace, scenario: 'Fixture', reference_id: 'SRC-FIXTURE', created_at: timestamp,
  })),
};

test.beforeEach(async ({ page }) => {
  await page.route('**/api/v1/simulation/catalog', (route) => route.fulfill({
    json: catalog, headers: { 'X-Correlation-ID': correlation },
  }));
  await page.route('**/api/v1/readiness', (route) => route.fulfill({
    status: 503,
    json: {
      mode: 'SYNTHETIC', status: 'not_ready', pilot: 'blocked',
      checks: { database: 'ready', worker: 'not_implemented', sync: 'not_implemented' },
    },
  }));
});

test('theme follows system and restores a keyboard-selected override', async ({ page }) => {
  await page.emulateMedia({ colorScheme: 'dark' });
  await page.goto('/');
  const theme = page.getByRole('combobox', { name: 'Tema' });
  const root = page.locator('html');
  await expect(theme).toHaveValue('system');
  await expect(root).toHaveAttribute('data-theme', 'system');
  await expect(page.locator('body')).toHaveCSS('background-color', 'rgb(16, 24, 34)');
  await page.keyboard.press('Tab');
  await expect(theme).toBeFocused();
  await page.keyboard.press('ArrowDown');
  await expect(theme).toHaveValue('light');
  await expect(page.locator('body')).toHaveCSS('background-color', 'rgb(243, 245, 247)');
  await page.reload();
  await expect(theme).toHaveValue('light');
  await theme.selectOption('system');
  await expect(page.locator('body')).toHaveCSS('background-color', 'rgb(16, 24, 34)');
});

for (const scheme of ['light', 'dark'] as const) {
  test(`desktop ${scheme} theme exposes semantic controls and contrast`, async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.goto('/');
    await page.getByRole('combobox', { name: 'Tema' }).selectOption(scheme);
    const picker = page.getByRole('combobox', { name: 'Kasus sintetis' });
    await expect(picker).toBeVisible();
    await expect(page.getByRole('group', { name: 'Workspace' }))
      .toMatchAriaSnapshot(`- group "Workspace":
  - button "Web Intelligence" [pressed]
  - button "USB Security"`);
    const ratio = await picker.evaluate((select) => {
      const styles = getComputedStyle(select);
      function luminance(color: string) {
        const channels = color.match(/[\d.]+/g)!.map(Number).slice(0, 3);
        const linear = channels.map((channel) => {
          const value = channel / 255;
          return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
        });
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2];
      }
      const first = luminance(styles.borderTopColor);
      const second = luminance(styles.backgroundColor);
      return (Math.max(first, second) + 0.05) / (Math.min(first, second) + 0.05);
    });
    expect(ratio).toBeGreaterThanOrEqual(3);
    const results = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze();
    expect(results.violations).toEqual([]);
  });
}

test('fixture links preserve each workspace selection and restore browser navigation', async ({ page }) => {
  await page.goto('/?case=SYN-012');
  const picker = page.getByRole('combobox', { name: 'Kasus sintetis' });
  await expect(picker).toHaveValue('SYN-012');
  await expect(page.getByRole('region', { name: 'Katalog kasus' }).locator('time')).toHaveAttribute('datetime', timestamp);
  await expect(page.getByText(correlation)).toBeVisible();
  const web = page.getByRole('button', { name: 'Web Intelligence' });
  const usb = page.getByRole('button', { name: 'USB Security' });
  await web.click();
  await picker.selectOption('SYN-002');
  await usb.click();
  await expect(picker).toHaveValue('SYN-012');
  await picker.selectOption('SYN-011');
  await web.click();
  await expect(picker).toHaveValue('SYN-002');
  await page.goBack();
  await expect(picker).toHaveValue('SYN-011');
  await expect(page.getByRole('link', { name: 'Tautan kasus sintetis' })).toHaveAttribute('href', /[?&]case=SYN-011$/);
});

test('saved case links require login and check access through the API', async ({ page }) => {
  let attempts = 0;
  await page.route('**/api/v1/sessions', (route) => route.fulfill({
    status: 201, json: { token: 'synthetic-session', user_id: ownerId, roles: ['supervisor'] },
  }));
  await page.route('**/api/v1/cases', (route) => route.fulfill({ json: [anotherCase] }));
  await page.route(`**/api/v1/cases/${savedId}`, (route) => {
    attempts++;
    expect(route.request().headers().authorization).toBe('Bearer synthetic-session');
    return route.fulfill({
      status: 404, json: { code: 'case_not_found' }, headers: { 'X-Correlation-ID': correlation },
    });
  });
  await page.goto(`/?saved=${savedId}`);
  await expect(page.getByRole('button', { name: 'Masuk' })).toBeVisible();
  expect(attempts).toBe(0);
  await page.getByLabel('Nama pengguna').fill('operator');
  await page.getByLabel('Kata sandi').fill('synthetic-password');
  await page.getByRole('button', { name: 'Masuk' }).click();
  const console = page.getByRole('region', { name: 'Kasus simulasi tersimpan' });
  await expect(console.getByRole('alert')).toHaveText('Kasus pada tautan tidak dapat dibuka.');
  await expect(console.getByText(correlation)).toBeVisible();
  await expect(console.getByRole('combobox', { name: 'Kasus tersimpan' })).toHaveValue('');
  await expect(console.getByRole('link', { name: 'Tautan kasus tersimpan' })).toHaveCount(0);
  expect(attempts).toBe(1);
});

test('an authorized saved case outside the list opens with its timestamps', async ({ page }) => {
  await page.route('**/api/v1/sessions', (route) => route.fulfill({
    status: 201, json: { token: 'synthetic-session', user_id: ownerId, roles: ['supervisor'] },
  }));
  await page.route('**/api/v1/cases', (route) => route.fulfill({ json: [anotherCase] }));
  await page.route(`**/api/v1/cases/${savedId}`, (route) => route.fulfill({
    json: { ...anotherCase, id: savedId, status: 'closed', closed_at: '2026-01-02T00:00:00Z' },
  }));
  await page.goto(`/?saved=${savedId}`);
  await page.getByLabel('Nama pengguna').fill('operator');
  await page.getByLabel('Kata sandi').fill('synthetic-password');
  await page.getByRole('button', { name: 'Masuk' }).click();
  const console = page.getByRole('region', { name: 'Kasus simulasi tersimpan' });
  const saved = console.getByRole('combobox', { name: 'Kasus tersimpan' });
  await expect(saved).toHaveValue(savedId);
  await expect(console.locator('time')).toHaveCount(2);
  await expect(console.getByRole('link', { name: 'Tautan kasus tersimpan' }))
    .toHaveAttribute('href', new RegExp(`[?&]saved=${savedId}$`));
  await saved.selectOption(anotherCase.id);
  await page.goBack();
  await expect(saved).toHaveValue(savedId);
});
