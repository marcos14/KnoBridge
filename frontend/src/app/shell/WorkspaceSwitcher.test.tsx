import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { makeMe, makeWorkspace, OTHER_WORKSPACE_ID, WORKSPACE_ID } from "@/test/factories";
import { meAs } from "@/test/handlers";
import { renderWithProviders } from "@/test/renderWithProviders";
import { server } from "@/test/server";

const twoWorkspaces = makeMe({
  workspaces: [
    makeWorkspace(),
    makeWorkspace({ id: OTHER_WORKSPACE_ID, name: "Beta Interno", role: "viewer" }),
  ],
});

describe("WorkspaceSwitcher", () => {
  it("test_workspace_switcher_shows_current_workspace", async () => {
    server.use(meAs(twoWorkspaces));
    renderWithProviders({ path: `/w/${WORKSPACE_ID}` });

    expect(await screen.findByRole("button", { name: "Trocar de workspace" })).toHaveTextContent(
      "Acme Suporte",
    );
  });

  it("test_workspace_switcher_changes_route_to_chosen_workspace", async () => {
    const user = userEvent.setup();
    server.use(meAs(twoWorkspaces));
    const { router } = renderWithProviders({ path: `/w/${WORKSPACE_ID}/sources` });

    await user.click(await screen.findByRole("button", { name: "Trocar de workspace" }));
    expect(screen.getByRole("menuitemradio", { name: "Acme Suporte" })).toHaveAttribute(
      "aria-checked",
      "true",
    );
    await user.click(screen.getByRole("menuitemradio", { name: "Beta Interno" }));

    expect(router.state.location.pathname).toBe(`/w/${OTHER_WORKSPACE_ID}`);
    expect(await screen.findByRole("button", { name: "Trocar de workspace" })).toHaveTextContent(
      "Beta Interno",
    );
  });

  it("test_workspace_switcher_flags_suspended_workspace", async () => {
    const user = userEvent.setup();
    server.use(
      meAs(
        makeMe({
          workspaces: [
            makeWorkspace(),
            makeWorkspace({ id: OTHER_WORKSPACE_ID, name: "Beta", status: "suspended" }),
          ],
        }),
      ),
    );
    renderWithProviders({ path: `/w/${WORKSPACE_ID}` });

    await user.click(await screen.findByRole("button", { name: "Trocar de workspace" }));

    expect(screen.getByRole("menuitemradio", { name: /Beta/ })).toHaveTextContent("suspenso");
  });

  it("test_workspace_switcher_shows_placeholder_outside_member_workspace", async () => {
    renderWithProviders({ path: `/w/${OTHER_WORKSPACE_ID}` });

    expect(await screen.findByRole("button", { name: "Trocar de workspace" })).toHaveTextContent(
      "Selecionar workspace",
    );
  });

  it("test_workspace_switcher_is_hidden_without_workspaces", async () => {
    server.use(meAs(makeMe({ workspaces: [] })));
    renderWithProviders({ path: "/account/profile" });

    await screen.findByRole("heading", { level: 1, name: "Perfil" });
    expect(screen.queryByRole("button", { name: "Trocar de workspace" })).not.toBeInTheDocument();
  });
});
