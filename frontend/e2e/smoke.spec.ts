import { expect, test } from "@playwright/test";

// Must not depend on the API: it may be absent, so the status indicator can show any state.
test("test_app_shell_loads", async ({ page }) => {
  await page.goto("/");

  await expect(page).toHaveTitle("KnoBridge");
  await expect(page.getByRole("main")).toBeVisible();
  await expect(page.getByRole("heading", { level: 1, name: "Início" })).toBeVisible();
  await expect(page.getByRole("status")).toBeVisible();
});
