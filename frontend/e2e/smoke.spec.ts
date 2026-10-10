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
  await expect(page.getByRole("heading", { level: 1, name: "Início" })).toBeVisible();
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
