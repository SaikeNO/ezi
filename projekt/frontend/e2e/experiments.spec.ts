import { expect, test } from "@playwright/test";

test("create variants, crawl, compare actual sets and render charts on desktop/mobile", async ({ page, request }) => {
  let id = ""; let sessions: string[] = [];
  const api = "http://127.0.0.1:18000/api";
  try {
    await page.goto("/experiments");
    await page.getByRole("textbox", { name: "Nazwa eksperymentu" }).fill("BFS i DFS — pomiar");
    await page.getByRole("textbox", { name: "Wspólny adres startowy" }).fill("http://site.example/");
    for (const letter of ["A", "B"]) {
      const group = page.getByRole("group", { name: "Wariant " + letter, exact: true });
      await group.getByRole("spinbutton", { name: "Limit stron", exact: true }).fill("3");
      await group.getByRole("spinbutton", { name: "Opóźnienie (ms)", exact: true }).fill("100");
    }
    await page.getByRole("button", { name: "Utwórz eksperyment", exact: true }).click();
    await expect(page).toHaveURL(/\/experiments\/[0-9a-f-]+$/);
    id = page.url().split("/").pop()!;
    const saved = await (await request.get(api + "/experiments/" + id)).json();
    sessions = saved.sessions.map((value: { id: string }) => value.id);
    await page.getByRole("button", { name: "Uruchom oczekujące warianty" }).click();
    await expect(page.getByRole("button", { name: "Porównaj warianty", exact: true })).toBeEnabled();
    await page.getByRole("button", { name: "Porównaj warianty", exact: true }).click();
    await expect(page.getByRole("heading", { name: "A względem B" })).toBeVisible();
    const result = await (await request.post(api + "/compare", { data: { session_ids: sessions } })).json();
    expect(result.pairs[0].fetched.left_only.items).toEqual(["http://site.example/b"]);
    expect(result.pairs[0].fetched.right_only.items).toEqual(["http://site.example/a1"]);
    await expect(page.getByRole("region", { name: "Wykres liczników" }).getByRole("application")).toBeVisible();
    await expect(page.getByRole("region", { name: "Wykres liczników" }).locator(".recharts-bar-rectangle")).toHaveCount(6);
    await expect(page.getByRole("region", { name: "Wykres czasu" }).getByRole("application")).toBeVisible();
    const fetched = page.getByRole("heading", { name: "Zbiory pobranych HTML" }).locator("..");
    await fetched.locator("summary", { hasText: "Tylko A: 1" }).click();
    await expect(fetched.getByText("http://site.example/b", { exact: true })).toBeVisible();
    await fetched.locator("summary", { hasText: "Tylko B: 1" }).click();
    await expect(fetched.getByText("http://site.example/a1", { exact: true })).toBeVisible();
    await page.screenshot({ path: "test-results/phase07-comparison-desktop.png", fullPage: true });
    await page.setViewportSize({ width: 375, height: 812 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: "test-results/phase07-comparison-mobile.png", fullPage: true });
    await page.reload();
    await expect(page.getByRole("button", { name: "Porównaj warianty", exact: true })).toBeEnabled();
    await page.getByRole("button", { name: "Porównaj warianty", exact: true }).click();
    await expect(page.getByRole("heading", { name: "A względem B" })).toBeVisible();
  } finally {
    if (id) await request.delete(api + "/experiments/" + id);
    for (const session of sessions) { await request.post(api + "/sessions/" + session + "/cancel"); await request.delete(api + "/sessions/" + session); }
  }
});

test("compare two existing sessions without experiment", async ({ page, request }) => {
  const api = "http://127.0.0.1:18000/api";
  const sessions: string[] = [];
  try {
    for (const mode of ["hyperlinks", "all_links"]) {
      const { id } = await (await request.post(api + "/sessions", { data: { start_url: "http://site.example/",
        config: { process_one_page: true, link_types: mode, request_delay_ms: 100 } } })).json();
      sessions.push(id); await request.post(api + "/sessions/" + id + "/start");
      await expect.poll(async () => (await (await request.get(api + "/sessions/" + id)).json()).status).toBe("completed");
    }
    await page.goto("/experiments");
    const picker = page.getByRole("region", { name: "Porównaj istniejące sesje" });
    for (const session of sessions) await picker.getByRole("checkbox", { name: new RegExp(session) }).check();
    await picker.getByRole("button", { name: "Porównaj wybrane sesje" }).click();
    await expect(picker.getByRole("heading", { name: "A względem B" })).toBeVisible();
    const result = await (await request.post(api + "/compare", { data: { session_ids: sessions } })).json();
    expect(result.pairs[0].edges.right_only.total).toBe(3);
    await expect(picker.getByText("link_types: hyperlinks → all_links", { exact: true })).toBeVisible();
  } finally {
    for (const id of sessions) { await request.post(api + "/sessions/" + id + "/cancel"); await request.delete(api + "/sessions/" + id); }
  }
});
