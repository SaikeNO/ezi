import { expect, test } from "@playwright/test";

test("create, persist, edit and delete session through real API", async ({
  page,
  request,
}) => {
  let sessionId: string | undefined;
  try {
    await page.goto("/sessions");
    await page
      .getByLabel("Adres startowy")
      .fill("https://example.com/phase-02-browser-test");
    await page.getByRole("combobox", { name: "Strategia", exact: true }).selectOption("dfs");
    await page.getByLabel("Maksymalna głębokość").fill("2");
    await page.getByLabel("Limit stron", { exact: true }).fill("25");
    await page
      .getByRole("button", { name: "Utwórz sesję", exact: true })
      .click();
    await expect(
      page.getByRole("heading", { name: "Szczegóły sesji" }),
    ).toBeVisible();
    sessionId = page.url().split("/").pop();
    await expect(page.getByText("DFS (w głąb)", { exact: true })).toBeVisible();
    await page.reload();
    await expect(page.getByText("DFS (w głąb)", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Edytuj konfigurację" }).click();
    await page.getByLabel("Limit stron", { exact: true }).fill("37");
    await page.getByRole("button", { name: "Zapisz zmiany" }).click();
    await expect(page.locator("dd").filter({ hasText: /^37$/ })).toBeVisible();
    const response = await request.get(
      `http://127.0.0.1:18000/api/sessions/${sessionId}`,
    );
    expect(response.status()).toBe(200);
    expect((await response.json()).config.max_pages).toBe(37);
    await page.setViewportSize({ width: 375, height: 812 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await page.screenshot({
      path: "test-results/phase02-detail-mobile.png",
      fullPage: true,
    });
    await page.getByRole("button", { name: "Usuń sesję", exact: true }).click();
    await page.getByRole("button", { name: "Potwierdź usunięcie" }).click();
    await expect(
      page.getByRole("heading", { name: "Nowa sesja" }),
    ).toBeVisible();
    expect(
      (
        await request.get(`http://127.0.0.1:18000/api/sessions/${sessionId}`)
      ).status(),
    ).toBe(404);
  } finally {
    if (sessionId)
      await request.delete(`http://127.0.0.1:18000/api/sessions/${sessionId}`);
  }
});

test("private start URL rejected without losing input", async ({ page }) => {
  await page.goto("/sessions");
  await page.getByLabel("Adres startowy").fill("http://127.0.0.1/");
  await page.getByRole("button", { name: "Utwórz sesję", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText(
    "Nieprawidłowe parametry",
  );
  await expect(page.getByLabel("Adres startowy")).toHaveValue(
    "http://127.0.0.1/",
  );
});
