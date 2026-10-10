import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { WORKSPACE_ID } from "@/test/factories";
import { setMobileViewport } from "@/test/matchMedia";
import { renderWithProviders } from "@/test/renderWithProviders";

async function renderShell(path = `/w/${WORKSPACE_ID}`) {
  const result = renderWithProviders({ path });
  await screen.findByRole("heading", { level: 1 });
  return result;
}

describe("AppShell", () => {
  it("test_app_shell_renders_landmarks", async () => {
    await renderShell();

    expect(screen.getByRole("banner")).toHaveTextContent("KnoBridge");
    expect(screen.getByRole("navigation", { name: "Navegação principal" })).toBeInTheDocument();
    expect(screen.getByRole("main")).toContainElement(
      screen.getByRole("heading", { level: 1, name: "Início" }),
    );
  });

  it("test_app_shell_header_has_api_status_and_user_menu", async () => {
    await renderShell();

    const banner = screen.getByRole("banner");
    expect(await within(banner).findByText("API: disponível")).toBeInTheDocument();
    expect(within(banner).getByRole("button", { name: "Menu do usuário" })).toBeInTheDocument();
  });

  it("test_app_shell_skip_link_is_first_and_targets_main", async () => {
    const user = userEvent.setup();
    await renderShell();

    await user.tab();

    const skipLink = screen.getByRole("link", { name: "Pular para o conteúdo" });
    expect(skipLink).toHaveFocus();
    expect(skipLink).toHaveAttribute("href", "#main-content");
    expect(screen.getByRole("main")).toHaveAttribute("id", "main-content");
  });

  it("test_app_shell_menu_is_reachable_by_keyboard", async () => {
    const user = userEvent.setup();
    const { router } = await renderShell();

    await user.tab();
    await user.tab();
    expect(screen.getByRole("button", { name: "Trocar de workspace" })).toHaveFocus();
    await user.tab();
    expect(screen.getByRole("link", { name: "Início" })).toHaveFocus();
    await user.tab();
    expect(screen.getByRole("link", { name: "Chat" })).toHaveFocus();
    await user.keyboard("{Enter}");

    expect(router.state.location.pathname).toBe(`/w/${WORKSPACE_ID}/chat`);
  });

  it("test_app_shell_toggle_collapses_and_expands_sidebar", async () => {
    const user = userEvent.setup();
    const { container } = await renderShell();
    const sidebar = container.querySelector('[data-slot="sidebar"]');

    expect(sidebar).toHaveAttribute("data-state", "expanded");
    await user.click(screen.getByRole("button", { name: "Mostrar ou ocultar o menu lateral" }));
    expect(sidebar).toHaveAttribute("data-state", "collapsed");
    await user.click(screen.getByRole("button", { name: "Mostrar ou ocultar o menu lateral" }));
    expect(sidebar).toHaveAttribute("data-state", "expanded");
  });

  it("test_app_shell_on_mobile_opens_menu_as_dialog_and_closes_after_navigation", async () => {
    const user = userEvent.setup();
    setMobileViewport(true);
    const { router } = await renderShell();

    expect(screen.queryByRole("navigation")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Mostrar ou ocultar o menu lateral" }));
    const dialog = await screen.findByRole("dialog", { name: "Menu lateral" });
    await user.click(within(dialog).getByRole("link", { name: "Fontes" }));

    expect(router.state.location.pathname).toBe(`/w/${WORKSPACE_ID}/sources`);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("test_app_shell_renders_not_found_inside_shell", async () => {
    await renderShell("/does-not-exist");

    expect(screen.getByRole("heading", { level: 1, name: "Página não encontrada" })).toBeVisible();
    expect(screen.getByRole("navigation", { name: "Navegação principal" })).toBeInTheDocument();
  });

  it("test_app_shell_renders_not_found_for_unknown_workspace_page", async () => {
    await renderShell(`/w/${WORKSPACE_ID}/unknown`);

    expect(screen.getByRole("main")).toHaveTextContent("Página não encontrada");
    expect(screen.getByRole("link", { name: "Início" })).toBeInTheDocument();
  });

  it("test_app_shell_renders_forbidden_inside_shell", async () => {
    await renderShell("/admin/workspaces");

    expect(screen.getByRole("main")).toContainElement(
      screen.getByRole("heading", { level: 1, name: "Acesso negado" }),
    );
    expect(screen.getByRole("banner")).toBeInTheDocument();
  });
});
