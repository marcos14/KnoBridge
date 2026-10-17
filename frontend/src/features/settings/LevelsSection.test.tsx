import { screen, waitFor, within } from "@testing-library/react";
import userEvent, { type UserEvent } from "@testing-library/user-event";
import { delay, http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import type { Role } from "@/lib/api/auth";
import { makeMe, makeWorkspace, OTHER_PROVIDER_ID, WORKSPACE_ID } from "@/test/factories";
import {
  levelStore,
  meAs,
  providersAs,
  providersServerError,
  updateLevelFails,
  workspaceLevelsServerError,
} from "@/test/handlers";
import { DEFAULT_LEVEL_INSTRUCTIONS, makeWorkspaceLevel } from "@/test/levelFactories";
import { renderWithProviders } from "@/test/renderWithProviders";
import { server } from "@/test/server";

const PATH = `/w/${WORKSPACE_ID}/settings`;
const SECTION = "Níveis de resposta";

async function renderLevels(role: Role = "owner") {
  server.use(meAs(makeMe({ workspaces: [makeWorkspace({ role })] })));
  const store = levelStore();
  server.use(...store.handlers);
  renderWithProviders({ path: PATH });
  const section = await screen.findByRole("region", { name: SECTION });
  await within(section).findByRole("form", { name: "Usuário final" });
  return { store, section };
}

function levelForm(name: string) {
  return screen.getByRole("form", { name });
}

function levelCard(name: string) {
  return screen.getByRole("article", { name });
}

async function choose(user: UserEvent, form: HTMLElement, label: string, option: string) {
  await user.click(within(form).getByRole("combobox", { name: label }));
  await user.click(await screen.findByRole("option", { name: option }));
}

describe("LevelsSection", () => {
  it("test_levels_section_lists_the_three_levels_with_cost_and_state", async () => {
    await renderLevels();

    const endUser = levelCard("Usuário final");
    expect(within(endUser).getByText("Configurado")).toBeInTheDocument();
    expect(within(endUser).getByText(/US\$\s0,00256 \(referência/)).toBeInTheDocument();
    expect(within(levelForm("Usuário final")).getByLabelText("Instruções do nível")).toHaveValue(
      DEFAULT_LEVEL_INSTRUCTIONS.end_user,
    );
    expect(within(endUser).getByText(/Usando o texto padrão do KnoBridge/)).toBeInTheDocument();

    const support = levelCard("Suporte");
    expect(within(support).getByText("Sem preço conhecido para este modelo.")).toBeInTheDocument();
    expect(within(support).getByText("Texto editado neste workspace.")).toBeInTheDocument();

    const dev = levelCard("Desenvolvimento e produto");
    expect(within(dev).queryByText("Configurado")).not.toBeInTheDocument();
    expect(
      within(dev).getByText(
        "Sem credencial e modelo: o chat neste nível não funciona até a configuração.",
      ),
    ).toBeInTheDocument();
  });

  it("test_levels_section_saves_model_and_temperature", async () => {
    const user = userEvent.setup();
    const { store } = await renderLevels();
    const form = levelForm("Usuário final");

    const model = within(form).getByRole("combobox", { name: "Modelo" });
    await user.clear(model);
    await user.type(model, "gpt-4.1");
    const temperature = within(form).getByLabelText("Temperatura");
    await user.clear(temperature);
    await user.type(temperature, "0,7");
    await user.click(within(form).getByRole("button", { name: "Salvar nível" }));

    expect(await within(form).findByText("Nível Usuário final atualizado.")).toHaveRole("status");
    expect(store.changes).toEqual([
      {
        level: "end_user",
        body: {
          provider_id: expect.any(String) as string,
          model: "gpt-4.1",
          temperature: 0.7,
          instructions: null,
          max_steps: 2,
        },
      },
    ]);
    expect(within(form).getByLabelText("Temperatura")).toHaveValue("0.7");
  });

  it("test_levels_section_restores_the_default_instructions", async () => {
    const user = userEvent.setup();
    const { store } = await renderLevels();
    const form = levelForm("Suporte");

    await user.click(within(form).getByRole("button", { name: "Restaurar padrão" }));

    expect(within(form).getByLabelText("Instruções do nível")).toHaveValue(
      DEFAULT_LEVEL_INSTRUCTIONS.support,
    );
    expect(
      within(form).queryByRole("button", { name: "Restaurar padrão" }),
    ).not.toBeInTheDocument();
    await user.click(within(form).getByRole("button", { name: "Salvar nível" }));

    await within(form).findByText("Nível Suporte atualizado.");
    expect(store.changes[0]?.body.instructions).toBeNull();
  });

  it("test_levels_section_edits_the_instructions", async () => {
    const user = userEvent.setup();
    const { store } = await renderLevels();
    const form = levelForm("Usuário final");

    const instructions = within(form).getByLabelText("Instruções do nível");
    await user.type(instructions, " Seja breve.");

    expect(within(form).getByText("Texto editado neste workspace.")).toBeInTheDocument();
    await user.click(within(form).getByRole("button", { name: "Salvar nível" }));

    await within(form).findByText("Nível Usuário final atualizado.");
    expect(store.changes[0]?.body.instructions).toBe(
      `${DEFAULT_LEVEL_INSTRUCTIONS.end_user} Seja breve.`,
    );
  });

  it("test_levels_section_configures_a_level_with_another_credential", async () => {
    const user = userEvent.setup();
    const { store } = await renderLevels();
    const form = levelForm("Desenvolvimento e produto");

    await choose(user, form, "Credencial", "Anthropic");
    await user.type(within(form).getByRole("combobox", { name: "Modelo" }), "claude-sonnet-5-5");
    await user.click(within(form).getByRole("button", { name: "Salvar nível" }));

    await within(form).findByText("Nível Desenvolvimento e produto atualizado.");
    expect(store.changes[0]?.body).toMatchObject({
      provider_id: OTHER_PROVIDER_ID,
      model: "claude-sonnet-5-5",
    });
    await waitFor(() => {
      expect(
        within(levelCard("Desenvolvimento e produto")).getByText("Configurado"),
      ).toBeInTheDocument();
    });
  });

  it("test_levels_section_suggests_models_of_the_credential_kind", async () => {
    const user = userEvent.setup();
    await renderLevels();
    const form = levelForm("Desenvolvimento e produto");
    const model = within(form).getByRole("combobox", { name: "Modelo" });
    const suggestions = () => {
      const list = document.getElementById(model.getAttribute("list") ?? "");
      return list === null
        ? []
        : within(list)
            .queryAllByRole("option", { hidden: true })
            .map((option) => option.getAttribute("value"));
    };

    expect(suggestions()).toEqual([]);
    await choose(user, form, "Credencial", "Anthropic");

    expect(suggestions()).toContain("claude-haiku-4-5");
  });

  it("test_levels_section_turns_a_level_off", async () => {
    const user = userEvent.setup();
    const { store } = await renderLevels();
    const form = levelForm("Usuário final");

    await choose(user, form, "Credencial", "Nenhuma (nível desligado)");
    await user.click(within(form).getByRole("button", { name: "Salvar nível" }));
    expect(
      await within(form).findByText("Escolha a credencial junto com o modelo."),
    ).toBeInTheDocument();

    await user.clear(within(form).getByRole("combobox", { name: "Modelo" }));
    await user.click(within(form).getByRole("button", { name: "Salvar nível" }));

    await within(form).findByText("Nível Usuário final atualizado.");
    expect(store.changes[0]?.body).toMatchObject({ provider_id: null, model: null });
    expect(
      await within(levelCard("Usuário final")).findByText(
        "Sem credencial e modelo: o chat neste nível não funciona até a configuração.",
      ),
    ).toBeInTheDocument();
  });

  it("test_levels_section_requires_a_model_with_a_credential", async () => {
    const user = userEvent.setup();
    const { store } = await renderLevels();
    const form = levelForm("Usuário final");

    await user.clear(within(form).getByRole("combobox", { name: "Modelo" }));
    await user.click(within(form).getByRole("button", { name: "Salvar nível" }));

    expect(
      await within(form).findByText("Informe o modelo junto com a credencial."),
    ).toBeInTheDocument();
    expect(store.changes).toEqual([]);
  });

  it("test_levels_section_shows_the_api_error", async () => {
    const user = userEvent.setup();
    await renderLevels();
    server.use(updateLevelFails(422, "level_provider_invalid"));
    const form = levelForm("Usuário final");

    await user.click(within(form).getByRole("button", { name: "Salvar nível" }));

    expect(await within(form).findByRole("alert")).toHaveTextContent(
      "Escolha uma credencial de LLM cadastrada neste workspace.",
    );
  });

  it("test_levels_section_disables_submit_while_saving", async () => {
    const user = userEvent.setup();
    await renderLevels();
    server.use(
      http.patch("*/v1/workspaces/:workspaceId/levels/:level", async () => {
        await delay("infinite");
        return HttpResponse.json(null);
      }),
    );
    const form = levelForm("Usuário final");

    await user.click(within(form).getByRole("button", { name: "Salvar nível" }));

    expect(await within(form).findByRole("button", { name: "Enviando…" })).toBeDisabled();
  });

  it("test_levels_section_without_credentials_points_to_providers", async () => {
    server.use(providersAs([]));
    const { section } = await renderLevels();

    expect(
      within(section).getByText(/Cadastre uma credencial de LLM para configurar os níveis./),
    ).toBeInTheDocument();
    expect(within(section).getByRole("link", { name: "Ir para provedores" })).toHaveAttribute(
      "href",
      `/w/${WORKSPACE_ID}/providers`,
    );
  });

  it("test_levels_section_retries_after_load_failure", async () => {
    const user = userEvent.setup();
    server.use(workspaceLevelsServerError, providersServerError);
    renderWithProviders({ path: PATH });
    const section = await screen.findByRole("region", { name: SECTION });

    expect(
      await within(section).findByText("Não foi possível carregar os níveis de resposta."),
    ).toHaveRole("alert");
    const store = levelStore();
    server.use(...store.handlers, providersAs());
    await user.click(within(section).getByRole("button", { name: "Tentar novamente" }));

    expect(await within(section).findByRole("form", { name: "Suporte" })).toBeInTheDocument();
  });

  it("test_levels_section_shows_loading_state", async () => {
    server.use(
      http.get("*/v1/workspaces/:workspaceId/levels", async () => {
        await delay("infinite");
        return HttpResponse.json(null);
      }),
    );
    renderWithProviders({ path: PATH });

    expect(await screen.findByText("Carregando os níveis…")).toHaveRole("status");
  });

  it("test_levels_section_shows_the_cost_with_every_search", async () => {
    await renderLevels();

    const endUser = levelCard("Usuário final");
    expect(within(endUser).getByText(/US\$\s0,00484 \(até 2 buscas/)).toBeInTheDocument();
    expect(
      within(levelForm("Usuário final")).getByRole("combobox", {
        name: "Máximo de buscas por resposta",
      }),
    ).toHaveTextContent("2 buscas");
    // Without a price there is no maximum cost either.
    expect(
      within(levelCard("Suporte")).queryByText("Com todas as buscas:"),
    ).not.toBeInTheDocument();
    expect(
      within(levelForm("Desenvolvimento e produto")).getByRole("combobox", {
        name: "Máximo de buscas por resposta",
      }),
    ).toHaveTextContent("4 buscas");
  });

  it("test_levels_section_saves_the_max_steps", async () => {
    const user = userEvent.setup();
    const { store } = await renderLevels();
    const form = levelForm("Suporte");

    await choose(user, form, "Máximo de buscas por resposta", "1 busca (sem busca em etapas)");
    await user.click(within(form).getByRole("button", { name: "Salvar nível" }));

    await within(form).findByText("Nível Suporte atualizado.");
    expect(store.changes[0]?.body.max_steps).toBe(1);
    expect(
      within(form).getByRole("combobox", { name: "Máximo de buscas por resposta" }),
    ).toHaveTextContent("1 busca (sem busca em etapas)");
  });

  it("test_levels_section_single_search_hides_the_maximum_cost", async () => {
    const store = levelStore([
      makeWorkspaceLevel({ max_steps: 1, estimated_max_cost_per_answer_usd: 0.00256 }),
    ]);
    server.use(...store.handlers);
    renderWithProviders({ path: PATH });

    const form = await screen.findByRole("form", { name: "Usuário final" });
    expect(within(levelCard("Usuário final")).queryByText("Com todas as buscas:")).toBeNull();
    expect(form).toBeInTheDocument();
  });

  it("test_levels_section_warns_when_the_model_has_no_tools", async () => {
    const store = levelStore([makeWorkspaceLevel({ tools_supported: false })]);
    server.use(...store.handlers);
    renderWithProviders({ path: PATH });

    await screen.findByRole("form", { name: "Usuário final" });
    expect(
      within(levelCard("Usuário final")).getByText(
        "O modelo deste nível não aceita busca em etapas; as respostas usam uma busca só.",
      ),
    ).toBeInTheDocument();
  });

  it("test_levels_section_admin_edits_the_levels", async () => {
    await renderLevels("admin");

    expect(
      within(levelForm("Suporte")).getByRole("button", { name: "Salvar nível" }),
    ).toBeEnabled();
  });
});
