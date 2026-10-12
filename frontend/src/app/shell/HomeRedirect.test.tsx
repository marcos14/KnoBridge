import { screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { storeLastWorkspaceId } from "@/lib/lastWorkspace";
import { makeMe, makeWorkspace, OTHER_WORKSPACE_ID, WORKSPACE_ID } from "@/test/factories";
import { meAs } from "@/test/handlers";
import { renderWithProviders } from "@/test/renderWithProviders";
import { server } from "@/test/server";

const twoWorkspaces = makeMe({
  workspaces: [makeWorkspace(), makeWorkspace({ id: OTHER_WORKSPACE_ID, name: "Beta" })],
});

describe("HomeRedirect", () => {
  it("test_home_redirect_opens_last_used_workspace", async () => {
    storeLastWorkspaceId(OTHER_WORKSPACE_ID);
    server.use(meAs(twoWorkspaces));
    const { router } = renderWithProviders({ path: "/" });

    await waitFor(() => {
      expect(router.state.location.pathname).toBe(`/w/${OTHER_WORKSPACE_ID}`);
    });
  });

  it("test_home_redirect_falls_back_to_first_workspace", async () => {
    storeLastWorkspaceId("00000000-0000-4000-8000-0000000000ff");
    server.use(meAs(twoWorkspaces));
    const { router } = renderWithProviders({ path: "/" });

    await waitFor(() => {
      expect(router.state.location.pathname).toBe(`/w/${WORKSPACE_ID}`);
    });
  });

  it("test_home_redirect_without_workspace_explains_situation", async () => {
    server.use(meAs(makeMe({ workspaces: [] })));
    renderWithProviders({ path: "/" });

    expect(
      await screen.findByRole("heading", {
        level: 1,
        name: "Você ainda não participa de nenhum workspace",
      }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: "Criar ou gerenciar workspaces" }),
    ).not.toBeInTheDocument();
  });

  it("test_home_redirect_without_workspace_offers_admin_shortcut_to_superadmin", async () => {
    server.use(meAs(makeMe({ workspaces: [], is_superadmin: true })));
    renderWithProviders({ path: "/" });

    expect(
      await screen.findByRole("link", { name: "Criar ou gerenciar workspaces" }),
    ).toHaveAttribute("href", "/admin/workspaces");
  });
});
