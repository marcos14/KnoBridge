import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { API_KEY_SECRET } from "@/test/apiKeyFactories";
import { WORKSPACE_ID } from "@/test/factories";
import { apiKeyStore } from "@/test/handlers";
import { renderWithProviders } from "@/test/renderWithProviders";
import { server } from "@/test/server";

const PATH = `/w/${WORKSPACE_ID}/api-keys`;

async function renderMcp() {
  const user = userEvent.setup();
  renderWithProviders({ path: PATH });
  const section = await screen.findByRole("region", { name: "Conectar por MCP" });
  return { user, section };
}

describe("ApiKeysPage MCP", () => {
  it("test_mcp_section_shows_the_server_url", async () => {
    const { user, section } = await renderMcp();
    const url = `${window.location.origin}/v1/mcp`;

    expect(within(section).getByText(url)).toBeVisible();
    await user.click(within(section).getByRole("button", { name: "Copiar a URL" }));
    await expect(navigator.clipboard.readText()).resolves.toBe(url);
  });

  it.each([
    ["Copiar o comando do Claude Code", "claude mcp add --transport http knobridge"],
    ["Copiar a configuração do Cursor", '"Authorization": "Bearer ${env:KNOBRIDGE_API_KEY}"'],
    ["Copiar a configuração do Codex", 'bearer_token_env_var = "KNOBRIDGE_API_KEY"'],
  ])("test_mcp_section_copies_%s", async (button, expected) => {
    const { user, section } = await renderMcp();

    await user.click(within(section).getByRole("button", { name: button }));

    const copied = await navigator.clipboard.readText();
    expect(copied).toContain(expected);
    expect(copied).toContain(`${window.location.origin}/v1/mcp`);
  });

  it("test_mcp_section_without_a_new_key_uses_a_placeholder", async () => {
    const { user, section } = await renderMcp();

    expect(
      within(section).getByText("Troque o valor pela chave mostrada ao criá-la."),
    ).toBeVisible();
    await user.click(within(section).getByRole("button", { name: "Copiar o comando da variável" }));

    await expect(navigator.clipboard.readText()).resolves.toContain(
      'export KNOBRIDGE_API_KEY="kbk_sua_chave"',
    );
  });

  it("test_mcp_commands_after_creating_a_key_set_the_new_key_once", async () => {
    const store = apiKeyStore([]);
    server.use(...store.handlers);
    const { user } = await renderMcp();

    await user.click(screen.getByRole("button", { name: "Nova chave" }));
    const form = await screen.findByRole("dialog", { name: "Nova chave de API" });
    await user.type(within(form).getByLabelText("Nome"), "claude-code");
    await user.click(within(form).getByRole("button", { name: "Salvar" }));
    const dialog = await screen.findByRole("dialog", { name: "Chave claude-code criada" });
    const section = within(dialog).getByRole("region", { name: "Conectar por MCP" });

    await user.click(within(section).getByRole("button", { name: "Copiar o comando da variável" }));
    await expect(navigator.clipboard.readText()).resolves.toContain(
      `export KNOBRIDGE_API_KEY="${API_KEY_SECRET}"`,
    );
    await user.click(
      within(section).getByRole("button", { name: "Copiar o comando do Claude Code" }),
    );
    // The client configuration reads the variable: the key is only in the line that sets it.
    await expect(navigator.clipboard.readText()).resolves.not.toContain(API_KEY_SECRET);
  });
});
