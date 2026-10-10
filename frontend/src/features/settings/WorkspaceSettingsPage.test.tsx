import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { delay, http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { makeMe, makeWorkspace, OTHER_WORKSPACE_ID, WORKSPACE_ID } from "@/test/factories";
import { meAs, renameWorkspaceFails } from "@/test/handlers";
import { renderWithProviders } from "@/test/renderWithProviders";
import { server } from "@/test/server";

import { WorkspaceSettingsPage } from "./WorkspaceSettingsPage";

const PATH = `/w/${WORKSPACE_ID}/settings`;
const WORKSPACE_PATH = "*/v1/workspaces/:workspaceId";

async function renderSettings() {
  const result = renderWithProviders({ path: PATH });
  await screen.findByRole("heading", { level: 1, name: "Configurações do workspace" });
  return result;
}

describe("WorkspaceSettingsPage", () => {
  it("test_workspace_settings_shows_name_and_read_only_slug", async () => {
    await renderSettings();

    expect(screen.getByLabelText("Nome do workspace")).toHaveValue("Acme Suporte");
    const slug = screen.getByLabelText("Identificador");
    expect(slug).toHaveValue("acme-suporte");
    expect(slug).toHaveAttribute("readonly");
  });

  it("test_workspace_settings_renames_and_updates_switcher", async () => {
    const user = userEvent.setup();
    const bodies: unknown[] = [];
    server.use(
      http.patch(WORKSPACE_PATH, async ({ request }) => {
        const body = (await request.json()) as { name: string };
        bodies.push(body);
        return HttpResponse.json({
          id: WORKSPACE_ID,
          name: body.name,
          slug: "acme-suporte",
          status: "active",
        });
      }),
    );
    await renderSettings();
    const name = screen.getByLabelText("Nome do workspace");

    await user.clear(name);
    await user.type(name, "  Acme Atendimento  ");
    await user.click(screen.getByRole("button", { name: "Salvar alterações" }));

    expect(await screen.findByText("Workspace atualizado.")).toHaveRole("status");
    expect(bodies).toEqual([{ name: "Acme Atendimento" }]);
    expect(name).toHaveValue("Acme Atendimento");
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /Trocar de workspace/ })).toHaveTextContent(
        "Acme Atendimento",
      );
    });
  });

  it("test_workspace_settings_requires_name", async () => {
    const user = userEvent.setup();
    await renderSettings();

    await user.clear(screen.getByLabelText("Nome do workspace"));
    await user.click(screen.getByRole("button", { name: "Salvar alterações" }));

    expect(await screen.findByText("Informe o nome do workspace.")).toBeInTheDocument();
  });

  it("test_workspace_settings_shows_api_error", async () => {
    const user = userEvent.setup();
    await renderSettings();
    server.use(renameWorkspaceFails(403, "forbidden"));

    await user.click(screen.getByRole("button", { name: "Salvar alterações" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Você não tem permissão para fazer isso.",
    );
  });

  it("test_workspace_settings_disables_submit_while_saving", async () => {
    const user = userEvent.setup();
    await renderSettings();
    server.use(
      http.patch(WORKSPACE_PATH, async () => {
        await delay("infinite");
        return HttpResponse.json(null);
      }),
    );

    await user.click(screen.getByRole("button", { name: "Salvar alterações" }));

    expect(await screen.findByRole("button", { name: "Salvando…" })).toBeDisabled();
  });

  it("test_workspace_settings_admin_can_open", async () => {
    server.use(meAs(makeMe({ workspaces: [makeWorkspace({ role: "admin" })] })));
    await renderSettings();

    expect(screen.getByRole("button", { name: "Salvar alterações" })).toBeEnabled();
  });

  it("test_workspace_settings_renders_only_title_without_membership", async () => {
    renderWithProviders({
      routes: [{ path: "/w/:workspaceId/settings", element: <WorkspaceSettingsPage /> }],
      path: `/w/${OTHER_WORKSPACE_ID}/settings`,
    });

    expect(
      await screen.findByRole("heading", { level: 1, name: "Configurações do workspace" }),
    ).toBeInTheDocument();
    expect(screen.queryByLabelText("Nome do workspace")).not.toBeInTheDocument();
  });
});
