import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { makeMe, makeWorkspace, OTHER_WORKSPACE_ID, WORKSPACE_ID } from "@/test/factories";
import { meAs } from "@/test/handlers";
import { renderWithProviders } from "@/test/renderWithProviders";
import { server } from "@/test/server";

function asMemberWithRole(role: "owner" | "admin" | "editor" | "viewer") {
  server.use(meAs(makeMe({ workspaces: [makeWorkspace({ role })] })));
}

describe("RequireWorkspaceRole", () => {
  it("test_require_workspace_role_lets_member_open_workspace", async () => {
    asMemberWithRole("viewer");
    renderWithProviders({ path: `/w/${WORKSPACE_ID}` });

    expect(await screen.findByRole("heading", { level: 1, name: "Início" })).toBeInTheDocument();
  });

  it("test_require_workspace_role_shows_403_for_non_member", async () => {
    const { router } = renderWithProviders({ path: `/w/${OTHER_WORKSPACE_ID}` });

    expect(
      await screen.findByRole("heading", { level: 1, name: "Acesso negado" }),
    ).toBeInTheDocument();
    expect(router.state.location.pathname).toBe(`/w/${OTHER_WORKSPACE_ID}`);
  });

  it("test_require_workspace_role_shows_403_for_insufficient_role", async () => {
    asMemberWithRole("editor");
    renderWithProviders({ path: `/w/${WORKSPACE_ID}/settings` });

    expect(
      await screen.findByRole("heading", { level: 1, name: "Acesso negado" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Voltar para o início" })).toHaveAttribute("href", "/");
  });

  it.each([
    ["viewer", "settings"],
    ["viewer", "assistants"],
    ["viewer", "providers"],
    ["editor", "conversations"],
    ["editor", "audit"],
  ] as const)("test_require_workspace_role_%s_cannot_open_%s", async (role, area) => {
    asMemberWithRole(role);
    renderWithProviders({ path: `/w/${WORKSPACE_ID}/${area}` });

    expect(
      await screen.findByRole("heading", { level: 1, name: "Acesso negado" }),
    ).toBeInTheDocument();
  });

  it.each([
    ["editor", "providers", "Provedores"],
    ["viewer", "members", "Membros"],
    ["viewer", "chat", "Chat"],
    ["admin", "conversations", "Conversas"],
  ] as const)("test_require_workspace_role_%s_opens_%s", async (role, area, title) => {
    asMemberWithRole(role);
    renderWithProviders({ path: `/w/${WORKSPACE_ID}/${area}` });

    expect(await screen.findByRole("heading", { level: 1, name: title })).toBeInTheDocument();
  });

  it("test_require_workspace_role_lets_sufficient_role_through", async () => {
    asMemberWithRole("admin");
    renderWithProviders({ path: `/w/${WORKSPACE_ID}/settings` });

    expect(
      await screen.findByRole("heading", { level: 1, name: "Configurações do workspace" }),
    ).toBeInTheDocument();
  });
});
