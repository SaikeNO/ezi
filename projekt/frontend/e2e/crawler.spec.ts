import { expect, test } from "@playwright/test";

test("real crawl: start, live progress, persisted page limit", async ({
  page,
  request,
}) => {
  const created = await request.post("http://127.0.0.1:18000/api/sessions", {
    data: {
      start_url: "http://site.example/",
      config: { max_pages: 3, request_delay_ms: 100 },
    },
  });
  const { id } = await created.json();
  const apiUrl = "http://127.0.0.1:18000/api/sessions/" + id;
  try {
    await page.goto("/sessions/" + id);
    await page.getByRole("button", { name: "Uruchom crawler" }).click();
    await expect(
      page.getByText("Osiągnięto limit prób pobrania stron."),
    ).toBeVisible();
    const stored = await (await request.get(apiUrl)).json();
    expect(stored.status).toBe("completed");
    expect(stored.fetched_count).toBe(3);
    await expect(
      page
        .locator("div")
        .filter({ has: page.locator("dt", { hasText: /^Pobrane HTML$/ }) })
        .last()
        .locator("dd"),
    ).toHaveText("3");
    await page.reload();
    await expect(
      page.getByText("Osiągnięto limit prób pobrania stron."),
    ).toBeVisible();
    await page.screenshot({
      path: "test-results/phase03-completed.png",
      fullPage: true,
    });
  } finally {
    await request.post(apiUrl + "/cancel");
    await request.delete(apiUrl);
  }
});

test("cancel pending request and retain partial state", async ({
  page,
  request,
}) => {
  const created = await request.post("http://127.0.0.1:18000/api/sessions", {
    data: {
      start_url: "http://site.example/slow",
      config: { request_delay_ms: 100 },
    },
  });
  const { id } = await created.json();
  const apiUrl = "http://127.0.0.1:18000/api/sessions/" + id;
  try {
    await page.goto("/sessions/" + id);
    await page.getByRole("button", { name: "Uruchom crawler" }).click();
    await expect(
      page.getByRole("button", { name: "Anuluj sesję" }),
    ).toBeEnabled();
    await page.getByRole("button", { name: "Anuluj sesję" }).click();
    await expect(
      page.getByText("Sesja anulowana. Częściowe wyniki zachowane."),
    ).toBeVisible();
    const result = await (await request.get(apiUrl)).json();
    expect(result.status).toBe("cancelled");
    expect(result.fetched_count).toBe(0);
    await page.setViewportSize({ width: 375, height: 812 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await page.screenshot({
      path: "test-results/phase03-cancelled-mobile.png",
      fullPage: true,
    });
  } finally {
    await request.post(apiUrl + "/cancel");
    await request.delete(apiUrl);
  }
});
