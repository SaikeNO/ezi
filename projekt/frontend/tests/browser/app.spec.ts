import { test, expect } from '@playwright/test';

test('crawl, graph, 12 experiments, datasets, exports and printable report', async ({
  page,
  request,
  context,
}) => {
  const errors: string[] = [];
  page.on('pageerror', (e) => errors.push(e.message));
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Zrozum strukturę sieci.' })).toBeVisible();
  await page.locator('.config-card input[type=url]').fill('http://127.0.0.1:8767/');
  await page.getByText('Ustawienia zaawansowane').click();
  await page.getByLabel('Opóźnienie [s]', { exact: true }).fill('0');
  await page.getByRole('button', { name: 'Rozpocznij badanie' }).click();
  await expect(page.locator('.study-bar .badge')).toHaveText('Zakończono', { timeout: 45000 });
  await expect(page.getByText('Spełnione', { exact: true })).toBeVisible();
  await page.screenshot({ path: 'test-results/overview.png', fullPage: true });
  await page.getByRole('button', { name: 'Graf WWW', exact: false }).click();
  await page.getByRole('button', { name: 'Przybliż', exact: true }).click();
  await expect(page.getByText('120%')).toBeVisible();
  await page.getByRole('button', { name: 'Adres http://127.0.0.1:8767/', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Szczegóły adresu' })).toBeVisible();
  await page.getByRole('button', { name: 'Zamknij szczegóły' }).click();
  await page.getByRole('button', { name: 'Eksperymenty', exact: true }).click();
  await page.getByRole('button', { name: 'Uruchom 12 wariantów' }).click();
  await expect(page.getByText('12 zakończonych', { exact: true })).toBeVisible({ timeout: 90000 });
  await expect(page.getByText(/Najwydajniejszy zmierzony wariant/)).toBeVisible();
  await page.screenshot({ path: 'test-results/experiments.png', fullPage: true });
  await page.getByRole('button', { name: 'Dane stron', exact: true }).click();
  await page.getByRole('button', { name: 'Przygotuj zbiory A/B' }).click();
  await expect(page.locator('.dataset-card .status-completed')).toHaveCount(2, { timeout: 45000 });
  const [download] = await Promise.all([
    page.waitForEvent('download'),
    page.getByRole('link', { name: 'Pobierz zbiór A' }).click(),
  ]);
  expect(download.suggestedFilename()).toMatch(/\.csv$/);
  const sqliteLink = await page.getByRole('link', { name: 'Pobierz zbiór B' }).getAttribute('href');
  const sqlite = await request.get(sqliteLink!);
  expect((await sqlite.body()).subarray(0, 15).toString()).toBe('SQLite format 3');
  await page.screenshot({ path: 'test-results/datasets.png', fullPage: true });
  await page.getByRole('button', { name: 'Raport', exact: true }).click();
  const [report] = await Promise.all([
    context.waitForEvent('page'),
    page.getByRole('link', { name: 'Otwórz i drukuj raport' }).click(),
  ]);
  await report.waitForLoadState();
  await expect(
    report.getByRole('heading', { name: '8. Porównanie baz i zastosowań' }),
  ).toBeVisible();
  await expect(report.locator('svg')).toBeVisible();
  await report.emulateMedia({ media: 'print' });
  await report.screenshot({ path: 'test-results/report.png', fullPage: true });
  await report.close();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole('button', { name: 'Przegląd', exact: true }).click();
  await page.screenshot({ path: 'test-results/mobile.png', fullPage: true });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
  expect(errors).toEqual([]);
});
