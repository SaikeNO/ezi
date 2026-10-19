import { expect, test } from "@playwright/test";
import type { Core, NodeSingular } from "cytoscape";

test("stored graph matches API; canvas selects, zooms, pans; search and mobile", async ({ page, request }) => {
  const base = "http://127.0.0.1:18000/api/sessions";
  const created = await request.post(base, { data: { start_url: "http://site.example/",
    config: { link_types: "all_links", request_delay_ms: 100 } } });
  const { id } = await created.json();
  const api = base + "/" + id;
  try {
    await request.post(api + "/start");
    await expect.poll(async () => (await (await request.get(api)).json()).status).toBe("completed");
    const graph = await (await request.get(api + "/graph")).json();
    expect(graph.summary.node_count).toBe(10);
    expect(graph.summary.link_count).toBe(11);
    await page.goto("/sessions/" + id);
    await page.getByRole("link", { name: "Otwórz graf sesji" }).click();
    const canvas = page.getByTestId("graph-canvas");
    await expect(canvas).toBeVisible();
    await canvas.scrollIntoViewIfNeeded();
    const readCanvas = () => page.evaluate(() => {
      const element = document.querySelector('[data-testid="graph-canvas"]') as HTMLElement & { _cyreg?: { cy: Core } };
      const cy = element?._cyreg?.cy;
      if (!cy) return null;
      const root = cy.nodes().filter(node => node.data("depth") === 0).first() as NodeSingular;
      return { nodes: cy.nodes().length, edges: cy.edges().length, zoom: cy.zoom(),
        pan: cy.pan(), root: root.renderedPosition() };
    });
    await expect.poll(async () => (await readCanvas())?.nodes).toBe(10);
    const initial = (await readCanvas())!;
    expect(initial.edges).toBe(11);
    const stats = page.getByRole("region", { name: "Statystyki grafu" });
    await expect(stats.locator("div").filter({ has: page.locator("dt", { hasText: /^Wystąpienia linków$/ }) }).locator("dd")).toHaveText("11");
    await page.getByRole("button", { name: "Dopasuj graf" }).click();
    await canvas.scrollIntoViewIfNeeded();
    const fitted = (await readCanvas())!;
    await canvas.click({ position: fitted.root });
    await expect(page.getByRole("region", { name: "Szczegóły węzła" })).toBeVisible();
    await expect(page.getByText("AA againB", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Powiększ", exact: true }).click();
    expect((await readCanvas())!.zoom).toBeGreaterThan(initial.zoom);
    const zoomed = (await readCanvas())!.zoom;
    await page.getByRole("button", { name: "Pomniejsz", exact: true }).click();
    expect((await readCanvas())!.zoom).toBeLessThan(zoomed);
    await page.getByRole("button", { name: "Dopasuj graf" }).click();
    const beforePan = (await readCanvas())!.pan;
    const box = (await canvas.boundingBox())!;
    await page.mouse.move(box.x + 8, box.y + 8); await page.mouse.down();
    await page.mouse.move(box.x + 68, box.y + 48, { steps: 8 }); await page.mouse.up();
    expect((await readCanvas())!.pan).not.toEqual(beforePan);
    await page.getByRole("button", { name: "Dopasuj graf" }).click();
    await page.getByRole("textbox", { name: "Szukaj węzła po URL lub tytule" }).fill("image.png");
    await page.getByRole("button", { name: "http://site.example/image.png", exact: true }).click();
    await expect(page.getByText(/Cel odnośnika bez rekordu/)).toBeVisible();
    await page.getByRole("button", { name: "Dopasuj graf" }).click();
    await page.screenshot({ path: "test-results/phase05-graph-desktop.png", fullPage: true });
    await page.reload(); await expect(canvas).toBeVisible();
    await page.setViewportSize({ width: 375, height: 812 });
    await page.getByRole("textbox").fill("/a11");
    await page.getByRole("button", { name: "http://site.example/a11", exact: true }).click();
    await expect(page.getByRole("region", { name: "Szczegóły węzła" })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.getByRole("button", { name: "Dopasuj graf" }).click();
    await page.screenshot({ path: "test-results/phase05-graph-mobile.png", fullPage: true });
  } finally {
    await request.post(api + "/cancel"); await request.delete(api);
  }
});

test("queued empty graph, chooser and missing session are honest", async ({ page, request }) => {
  const base = "http://127.0.0.1:18000/api/sessions";
  const { id } = await (await request.post(base, { data: { start_url: "https://example.com/" } })).json();
  try {
    await page.goto("/graph");
    await expect(page.getByRole("heading", { name: "Wybierz zapisaną sesję" })).toBeVisible();
    await page.goto("/graph/" + id);
    await expect(page.getByText(/Brak zapisanych węzłów/)).toBeVisible();
    await request.delete(base + "/" + id);
    await page.getByRole("button", { name: "Odśwież graf" }).click();
    await expect(page.getByRole("alert")).toHaveText("Nie znaleziono sesji");
  } finally { await request.delete(base + "/" + id); }
});
