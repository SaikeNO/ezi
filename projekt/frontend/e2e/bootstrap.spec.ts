import { test, expect } from "@playwright/test"

test("real API health, Polish navigation, mobile layout", async ({ page }) => {
  await page.goto("/")
  await expect(page.getByText("Backend działa", { exact: true })).toBeVisible()
  await expect(page.getByText("SQLite: połączenie aktywne")).toBeVisible()
  await expect(page.locator("html")).toHaveAttribute("lang", "pl")
  await page.getByRole("button", { name: "Sprawdź ponownie" }).click()
  await expect(page.getByText("Backend działa", { exact: true })).toBeVisible()
  await page.getByRole("link", { name: "Sesje", exact: true }).click()
  await expect(page.getByRole("heading", { name: "Sesje", exact: true })).toBeVisible()
  await page.reload()
  await expect(page.getByRole("heading", { name: "Sesje", exact: true })).toBeVisible()
  await page.setViewportSize({ width: 375, height: 812 })
  await page.getByRole("link", { name: "Przegląd", exact: true }).click()
  await expect(page.getByText("Backend działa", { exact: true })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
})

test("unreachable backend shown honestly", async ({ page }) => {
  await page.route("**/health", route => route.abort())
  await page.goto("/")
  await expect(page.getByText("Brak połączenia z backendem")).toBeVisible()
})
