import { expect, test } from "@playwright/test";

// Must not depend on the API: it may be absent, so the status indicator can show any state. The
// guards ask the API whether the instance is set up and who is logged in; those two answers are
// synthetic, served by the browser itself.
test("test_app_shell_loads", async ({ page }) => {
  await page.route("**/v1/setup/status", (route) =>
    route.fulfill({ json: { needs_setup: false } }),
  );
  await page.route("**/v1/me", (route) =>
    route.fulfill({
      json: {
        user: {
          id: "00000000-0000-4000-8000-000000000001",
          email: "ana@example.test",
          name: "Ana Teste",
          locale: "pt-BR",
          theme: "system",
          email_verified_at: "2026-01-01T00:00:00Z",
        },
        is_superadmin: false,
        workspaces: [],
      },
    }),
  );

  await page.goto("/");

  await expect(page).toHaveTitle("KnoBridge");
  await expect(page.getByRole("main")).toBeVisible();
  await expect(
    page.getByRole("heading", { level: 1, name: "Você ainda não participa de nenhum workspace" }),
  ).toBeVisible();
  // Without workspaces the menu has no items; the shell still offers its toggle.
  await expect(
    page.getByRole("button", { name: "Mostrar ou ocultar o menu lateral" }),
  ).toBeVisible();
  await expect(page.getByRole("status")).toBeVisible();
});

test("test_anonymous_user_is_sent_to_login", async ({ page }) => {
  await page.route("**/v1/setup/status", (route) =>
    route.fulfill({ json: { needs_setup: false } }),
  );
  await page.route("**/v1/me", (route) =>
    route.fulfill({
      status: 401,
      json: { error: { code: "unauthenticated", message: "No session.", details: null } },
    }),
  );

  await page.goto("/account");

  await expect(page.getByRole("heading", { level: 1, name: "Entrar" })).toBeVisible();
  await expect(page).toHaveURL(/\/login\?next=%2Faccount$/);
});

// The inline script of index.html paints the saved theme before the app loads (no white flash).
test("test_saved_dark_theme_is_applied_before_the_app_loads", async ({ page }) => {
  // A string runs in the page; e2e/ is type-checked without the DOM library.
  await page.addInitScript('window.localStorage.setItem("knobridge-theme", "dark");');
  await page.route("**/v1/**", (route) => route.abort());

  await page.goto("/login");

  await expect(page.locator("html")).toHaveClass("dark");
});
