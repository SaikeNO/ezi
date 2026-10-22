import { readFile } from "node:fs/promises";
import { expect, test } from "@playwright/test";

test("lab site: dashboard, reports, CSV, graph, comparison, persistence and mobile", async ({ page, request }) => {
  const api = "http://127.0.0.1:18000/api";
  const ids: string[] = [];
  try {
    for (const config of [{ max_depth: 3 }, { max_depth: 2, scope: "web", follow_external_urls: true }]) {
      const response = await request.post(api + "/sessions", { data: { start_url: "http://site.example/lab/", config: { request_delay_ms: 100, ...config } } });
      expect(response.status()).toBe(201);
      const { id } = await response.json(); ids.push(id);
      expect((await request.post(api + `/sessions/${id}/start`)).ok()).toBeTruthy();
      await expect.poll(async () => (await (await request.get(api + `/sessions/${id}`)).json()).status).toBe("completed");
    }
    const stats = await (await request.get(api + `/sessions/${ids[0]}/stats`)).json();
    expect(stats.summary.fetched_pages).toBe(22); expect(stats.summary.reached_depth).toBe(3);
    await page.goto("/");
    const dashboard = page.getByRole("region", { name: "Dashboard zapisanych wyników" });
    await expect(dashboard.getByText("http://site.example/lab/", { exact: true })).toHaveCount(2);
    await page.goto(`/sessions/${ids[0]}`);
    const pending = page.waitForEvent("download");
    await page.getByRole("button", { name: "Pobierz raport sesji HTML" }).click();
    const download = await pending;
    expect(download.suggestedFilename()).toBe(`report-${ids[0]}.html`);
    const html = await readFile((await download.path())!, "utf8");
    expect(html).toContain("reached_depth</td><td>3");
    expect(html).toContain("Keyword</td><td>16</td><td>6");
    // Render downloaded report in browser for visual/accessibility/layout QA.
    await page.route("**/qa-report", route => route.fulfill({ contentType: "text/html; charset=utf-8", body: html }));
    await page.goto("/qa-report");
    await expect(page.getByRole("heading", { name: "Raport sesji — WebCrawler Studio" })).toBeVisible();
    await page.screenshot({ path: "test-results/phase08-report-desktop.png", fullPage: true });
    expect(await page.locator("script").count()).toBe(0);
    await page.setViewportSize({ width: 375, height: 812 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: "test-results/phase08-report-mobile.png", fullPage: true });
    await page.setViewportSize({ width: 1280, height: 720 });
    await page.goto(`/graph/${ids[0]}`);
    await expect(page.getByRole("heading", { name: /Graf witryny/ })).toBeVisible();
    await page.goto("/experiments");
    const picker = page.getByRole("region", { name: "Porównaj istniejące sesje" });
    for (const id of ids) await picker.getByRole("checkbox", { name: new RegExp(id) }).check();
    await picker.getByRole("button", { name: "Porównaj wybrane sesje" }).click();
    await expect(picker.getByRole("heading", { name: "A względem B" })).toBeVisible();
    const comparisonPending = page.waitForEvent("download");
    await page.getByRole("button", { name: "Pobierz raport porównania HTML" }).click();
    const comparisonDownload = await comparisonPending;
    const compared = await readFile((await comparisonDownload.path())!, "utf8");
    expect(compared).toContain("Pobrane HTML</td><td>10</td><td>12</td><td>1");
    await page.route("**/qa-comparison", route => route.fulfill({ contentType: "text/html; charset=utf-8", body: compared }));
    await page.goto("/qa-comparison");
    await page.screenshot({ path: "test-results/phase08-comparison-desktop.png", fullPage: true });
    await page.setViewportSize({ width: 375, height: 812 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: "test-results/phase08-comparison-mobile.png", fullPage: true });
    await page.goto("/");
    await page.reload();
    await expect(dashboard.getByText("http://site.example/lab/", { exact: true })).toHaveCount(2);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: "test-results/phase08-dashboard-mobile.png", fullPage: true });
    const csv = await request.get(api + `/sessions/${ids[1]}/export?fields=url,keywords&separator=semicolon`);
    expect((await csv.text()).replace(/^\uFEFF/, "")).toMatch(/^URL;Keyword/);
  } finally {
    for (const id of ids) { await request.post(api + `/sessions/${id}/cancel`); await request.delete(api + `/sessions/${id}`); }
  }
});

test("dashboard unavailable, retry and explicit empty response", async ({ page }) => {
  await page.route("**/api/dashboard", route => route.abort());
  await page.goto("/");
  const dashboard = page.getByRole("region", { name: "Dashboard zapisanych wyników" });
  await expect(dashboard.getByRole("alert")).toBeVisible();
  await page.unroute("**/api/dashboard");
  // Other suites retain sessions; exercise empty UI with an explicit intercepted response.
  await page.route("**/api/dashboard", route => route.fulfill({ json: {
    sessions: 0, discovered_pages: 0, fetched_pages: 0, errored_pages: 0, links: 0, recent: [],
    statuses: { queued: 0, running: 0, completed: 0, failed: 0, cancelled: 0 },
  } }));
  await page.getByRole("button", { name: "Odśwież dashboard" }).click();
  await expect(dashboard.getByText(/Brak sesji/)).toBeVisible();
});
