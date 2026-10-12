import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { storeLastWorkspaceId } from "@/lib/lastWorkspace";
import { makeMe, makeWorkspace, OTHER_WORKSPACE_ID, WORKSPACE_ID } from "@/test/factories";
import { meAs } from "@/test/handlers";
import { renderWithProviders } from "@/test/renderWithProviders";
import { server } from "@/test/server";

type Role = "owner" | "admin" | "editor" | "viewer";

async function renderMenu(role: Role, path = `/w/${WORKSPACE_ID}`) {
  server.use(meAs(makeMe({ workspaces: [makeWorkspace({ role })] })));
  const result = renderWithProviders({ path });
  const nav = await screen.findByRole("navigation", { name: "Navegação principal" });
  return { ...result, nav };
}

function linkNames(nav: HTMLElement): string[] {
  return within(nav)
    .getAllByRole("link")
    .map((link) => link.textContent);
}

describe("AppSidebar", () => {
  it("test_app_sidebar_viewer_sees_members_but_not_management", async () => {
    const { nav } = await renderMenu("viewer");

    expect(linkNames(nav)).toEqual([
      "Início",
      "Chat",
      "Fontes",
      "Pipelines",
      "Coleções",
      "Canais",
      "Membros",
    ]);
  });

  it("test_app_sidebar_editor_sees_assistants_and_providers_but_not_settings", async () => {
    const { nav } = await renderMenu("editor");

    expect(within(nav).getByRole("link", { name: "Assistentes" })).toBeInTheDocument();
    expect(within(nav).getByRole("link", { name: "Provedores" })).toBeInTheDocument();
    expect(within(nav).queryByRole("link", { name: "Configurações" })).not.toBeInTheDocument();
    expect(within(nav).queryByRole("link", { name: "Conversas" })).not.toBeInTheDocument();
  });

  it("test_app_sidebar_admin_sees_members_settings_and_audit", async () => {
    const { nav } = await renderMenu("admin");

    expect(within(nav).getByRole("link", { name: "Membros" })).toHaveAttribute(
      "href",
      `/w/${WORKSPACE_ID}/members`,
    );
    expect(within(nav).getByRole("link", { name: "Configurações" })).toBeInTheDocument();
    expect(within(nav).getByRole("link", { name: "Auditoria" })).toBeInTheDocument();
    expect(within(nav).getByRole("link", { name: "Conversas" })).toBeInTheDocument();
  });

  it("test_app_sidebar_hides_instance_admin_from_regular_user", async () => {
    const { nav } = await renderMenu("owner");

    expect(within(nav).queryByText("Administração da instância")).not.toBeInTheDocument();
  });

  it("test_app_sidebar_superadmin_sees_instance_admin", async () => {
    server.use(meAs(makeMe({ is_superadmin: true })));
    renderWithProviders({ path: `/w/${WORKSPACE_ID}` });
    const nav = await screen.findByRole("navigation", { name: "Navegação principal" });

    expect(within(nav).getByText("Administração da instância")).toBeInTheDocument();
    expect(within(nav).getByRole("link", { name: "Workspaces" })).toHaveAttribute(
      "href",
      "/admin/workspaces",
    );
    expect(within(nav).getByRole("link", { name: "Usuários" })).toBeInTheDocument();
  });

  it("test_app_sidebar_marks_current_area", async () => {
    const { nav } = await renderMenu("viewer", `/w/${WORKSPACE_ID}/sources`);

    expect(within(nav).getByRole("link", { name: "Fontes" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(within(nav).getByRole("link", { name: "Início" })).not.toHaveAttribute("aria-current");
  });

  it("test_app_sidebar_link_navigates_to_area", async () => {
    const user = userEvent.setup();
    const { nav, router } = await renderMenu("viewer");

    await user.click(within(nav).getByRole("link", { name: "Pipelines" }));

    expect(router.state.location.pathname).toBe(`/w/${WORKSPACE_ID}/pipelines`);
    expect(await screen.findByRole("heading", { level: 1, name: "Pipelines" })).toBeInTheDocument();
  });

  it("test_app_sidebar_outside_workspace_shows_last_used_workspace", async () => {
    storeLastWorkspaceId(OTHER_WORKSPACE_ID);
    server.use(
      meAs(
        makeMe({
          workspaces: [makeWorkspace(), makeWorkspace({ id: OTHER_WORKSPACE_ID, role: "viewer" })],
        }),
      ),
    );
    renderWithProviders({ path: "/account/profile" });
    const nav = await screen.findByRole("navigation", { name: "Navegação principal" });

    expect(within(nav).getByRole("link", { name: "Início" })).toHaveAttribute(
      "href",
      `/w/${OTHER_WORKSPACE_ID}`,
    );
    expect(within(nav).queryByRole("link", { name: "Configurações" })).not.toBeInTheDocument();
  });

  it("test_app_sidebar_without_membership_in_url_workspace_shows_no_workspace_items", async () => {
    renderWithProviders({ path: `/w/${OTHER_WORKSPACE_ID}` });

    expect(
      await screen.findByRole("heading", { level: 1, name: "Acesso negado" }),
    ).toBeInTheDocument();
    const nav = screen.getByRole("navigation", { name: "Navegação principal" });
    expect(within(nav).queryAllByRole("link")).toHaveLength(0);
  });
});
