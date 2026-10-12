import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { type Me, meQueryKey, type ProfileUpdate } from "@/lib/api/auth";
import { THEME_STORAGE_KEY } from "@/lib/theme";
import { makeMe, WORKSPACE_ID } from "@/test/factories";
import { logoutCsrfFailed, meAs, updateProfileCsrfFailed } from "@/test/handlers";
import { matchMediaListenerCount, setPrefersDark } from "@/test/matchMedia";
import { renderWithProviders } from "@/test/renderWithProviders";
import { server } from "@/test/server";

function meWithTheme(theme: "light" | "dark" | "system"): Me {
  const me = makeMe();
  return { ...me, user: { ...me.user, theme } };
}

async function openUserMenu(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByRole("button", { name: "Menu do usuário" }));
}

describe("UserMenu", () => {
  it("test_user_menu_shows_name_email_and_initials", async () => {
    const user = userEvent.setup();
    renderWithProviders({ path: `/w/${WORKSPACE_ID}` });

    const trigger = await screen.findByRole("button", { name: "Menu do usuário" });
    expect(trigger).toHaveTextContent("AT");
    await openUserMenu(user);

    expect(screen.getByRole("menu")).toHaveTextContent("Ana Teste");
    expect(screen.getByRole("menu")).toHaveTextContent("ana@example.test");
  });

  it.each([
    ["Perfil", "/account/profile"],
    ["Segurança", "/account/security"],
  ])("test_user_menu_%s_opens_account_page", async (name, pathname) => {
    const user = userEvent.setup();
    const { router } = renderWithProviders({ path: `/w/${WORKSPACE_ID}` });

    await openUserMenu(user);
    await user.click(screen.getByRole("menuitem", { name }));

    expect(router.state.location.pathname).toBe(pathname);
    expect(await screen.findByRole("heading", { level: 1, name })).toBeInTheDocument();
  });

  it("test_user_menu_theme_switches_and_persists_in_profile_and_storage", async () => {
    const user = userEvent.setup();
    const bodies: ProfileUpdate[] = [];
    server.use(
      http.patch("*/v1/me", async ({ request }) => {
        const body = (await request.json()) as ProfileUpdate;
        bodies.push(body);
        return HttpResponse.json<Me>(meWithTheme(body.theme ?? "system"));
      }),
    );
    renderWithProviders({ path: `/w/${WORKSPACE_ID}` });

    await openUserMenu(user);
    expect(screen.getByRole("menuitemradio", { name: "Sistema" })).toHaveAttribute(
      "aria-checked",
      "true",
    );
    await user.click(screen.getByRole("menuitemradio", { name: "Escuro" }));

    await waitFor(() => {
      expect(document.documentElement).toHaveClass("dark");
    });
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe("dark");
    await waitFor(() => {
      expect(bodies).toEqual([{ theme: "dark" }]);
    });

    await openUserMenu(user);
    expect(screen.getByRole("menuitemradio", { name: "Escuro" })).toHaveAttribute(
      "aria-checked",
      "true",
    );
    await user.click(screen.getByRole("menuitemradio", { name: "Claro" }));

    await waitFor(() => {
      expect(document.documentElement).not.toHaveClass("dark");
    });
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe("light");
  });

  it("test_user_menu_applies_profile_theme_on_load", async () => {
    server.use(meAs(meWithTheme("dark")));
    renderWithProviders({ path: `/w/${WORKSPACE_ID}` });

    await screen.findByRole("button", { name: "Menu do usuário" });

    expect(document.documentElement).toHaveClass("dark");
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe("dark");
  });

  it("test_user_menu_system_theme_follows_os_changes", async () => {
    const { unmount } = renderWithProviders({ path: `/w/${WORKSPACE_ID}` });
    await screen.findByRole("button", { name: "Menu do usuário" });
    expect(document.documentElement).not.toHaveClass("dark");

    setPrefersDark(true);

    expect(document.documentElement).toHaveClass("dark");
    unmount();
    expect(matchMediaListenerCount()).toBe(0);
  });

  it("test_user_menu_theme_reverts_when_profile_update_fails", async () => {
    const user = userEvent.setup();
    server.use(meAs(meWithTheme("light")), updateProfileCsrfFailed);
    renderWithProviders({ path: `/w/${WORKSPACE_ID}` });

    await openUserMenu(user);
    await user.click(screen.getByRole("menuitemradio", { name: "Escuro" }));

    await waitFor(() => {
      expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe("light");
    });
    expect(document.documentElement).not.toHaveClass("dark");
  });

  it("test_user_menu_logout_goes_to_plain_login_without_next", async () => {
    const user = userEvent.setup();
    const { router, queryClient } = renderWithProviders({ path: `/w/${WORKSPACE_ID}/sources` });

    await openUserMenu(user);
    await user.click(screen.getByRole("menuitem", { name: "Sair" }));

    expect(await screen.findByRole("heading", { level: 1, name: "Entrar" })).toBeInTheDocument();
    await waitFor(() => {
      expect(queryClient.getQueryData(meQueryKey)).toBeNull();
    });
    expect(router.state.location.pathname).toBe("/login");
    expect(router.state.location.search).toBe("");
  });

  it("test_user_menu_failed_logout_keeps_user_on_page", async () => {
    const user = userEvent.setup();
    server.use(logoutCsrfFailed);
    const { router } = renderWithProviders({ path: `/w/${WORKSPACE_ID}` });

    await openUserMenu(user);
    await user.click(screen.getByRole("menuitem", { name: "Sair" }));

    expect(await screen.findByRole("button", { name: "Menu do usuário" })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe(`/w/${WORKSPACE_ID}`);
  });
});
