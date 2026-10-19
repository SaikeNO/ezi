import { expect, test } from "@playwright/test";
import { readFile } from "node:fs/promises";

test("real crawl data: pagination, filters, metadata and downloaded CSV", async ({ page, request }) => {
  const base = "http://127.0.0.1:18000/api/sessions";
  const { id } = await (await request.post(base, { data: { start_url: "http://site.example/csv",
    config: { request_delay_ms: 100 } } })).json();
  const api = base + "/" + id;
  try {
    await request.post(api + "/start");
    await expect.poll(async () => (await (await request.get(api)).json()).status).toBe("completed");
    await page.goto("/sessions/" + id);
    await page.getByRole("link", { name: "Dane i eksport CSV" }).click();
    await expect(page.getByText("Pasujące strony: 13.", { exact: false })).toBeVisible();
    await page.getByRole("button", { name: "Następne strony" }).click();
    await expect(page.getByText("Od 11 do 13 z 13")).toBeVisible();
    await page.getByRole("button", { name: "Poprzednie strony" }).click();
    await page.getByRole("button", { name: "Treść strony http://site.example/csv", exact: true }).click();
    await expect(page.getByRole("region", { name: "Zapisana treść strony" }).getByText("Opis & dane", { exact: true })).toBeVisible();
    await page.getByRole("textbox", { name: "Szukaj w URL i metadanych" }).fill("ZAŻÓŁĆ");
    await page.getByRole("button", { name: "Zastosuj filtry" }).click();
    await expect(page.getByText("Pasujące strony: 1.", { exact: false })).toBeVisible();
    await page.getByRole("checkbox", { name: "Title", exact: true }).check();
    await page.getByRole("checkbox", { name: "Body", exact: true }).check();
    await page.getByRole("combobox", { name: "Separator" }).selectOption("semicolon");
    const downloadEvent = page.waitForEvent("download");
    await page.getByRole("button", { name: "Pobierz CSV" }).click();
    const download = await downloadEvent;
    expect(download.suggestedFilename()).toBe("crawl-" + id + ".csv");
    const bytes = await readFile((await download.path())!);
    expect([...bytes.subarray(0, 3)]).toEqual([239, 187, 191]);
    const csv = bytes.toString("utf8");
    expect(csv).toContain("URL;Keyword;Title;Body\r\n");
    expect(csv).toContain("'=1+1");
    expect(csv).toContain('"Zażółć, ""gęślą""; jaźń"');
    expect(csv).not.toContain("http://site.example/csv/0");
    await page.screenshot({ path: "test-results/phase06-explorer-desktop.png", fullPage: true });
    await page.setViewportSize({ width: 375, height: 812 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: "test-results/phase06-explorer-mobile.png", fullPage: true });
    await page.getByRole("button", { name: "Wyczyść filtry" }).click();
    await expect(page.getByText("Pasujące strony: 13.", { exact: false })).toBeVisible();
    await page.reload();
    await expect(page.getByRole("heading", { name: "Eksplorator danych" })).toBeVisible();
  } finally { await request.post(api + "/cancel"); await request.delete(api); }
});

test("explorer chooser, empty session and failed export", async ({ page, request }) => {
  const base = "http://127.0.0.1:18000/api/sessions";
  const { id } = await (await request.post(base, { data: { start_url: "https://example.com/" } })).json();
  try {
    await page.goto("/data");
    await expect(page.getByRole("heading", { name: "Wybierz sesję do eksploracji" })).toBeVisible();
    await page.goto("/data/" + id);
    await expect(page.getByText("Brak stron dla wybranych filtrów.")).toBeVisible();
    await request.delete(base + "/" + id);
    await page.getByRole("button", { name: "Pobierz CSV" }).click();
    await expect(page.getByRole("alert")).toHaveText("Nie znaleziono sesji");
  } finally { await request.delete(base + "/" + id); }
});
