import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { delay, http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import type { Role } from "@/lib/api/auth";
import {
  ASSISTANT_ID,
  makeAssistant,
  makeMe,
  makeWorkspace,
  OTHER_ASSISTANT_ID,
  OTHER_WORKSPACE_ID,
  PROVIDER_ID,
  WORKSPACE_ID,
} from "@/test/factories";
import {
  assistantsAs,
  assistantsOk,
  assistantsServerError,
  assistantStore,
  createAssistantFails,
  DEFAULT_NO_SOURCE_MESSAGE,
  deleteAssistantFails,
  meAs,
  providersAs,
  updateAssistantFails,
} from "@/test/handlers";
import { renderWithProviders } from "@/test/renderWithProviders";
import { server } from "@/test/server";

import { AssistantsPage } from "./AssistantsPage";

const PATH = `/w/${WORKSPACE_ID}/assistants`;
const TABLE = "Assistentes do workspace";

type User = ReturnType<typeof userEvent.setup>;

function asRole(role: Role) {
  server.use(meAs(makeMe({ workspaces: [makeWorkspace({ role })] })));
}

async function renderAssistants() {
  const result = renderWithProviders({ path: PATH });
  await screen.findByRole("table", { name: TABLE });
  return result;
}

function rowOf(name: string): HTMLElement {
  const row = within(screen.getByRole("table", { name: TABLE }))
    .getAllByRole("row")
    .find((item) => item.textContent.includes(name));
  if (row === undefined) {
    throw new Error(`No row for ${name}`);
  }
  return row;
}

async function openCreate(user: User) {
  await user.click(screen.getByRole("button", { name: "Novo assistente" }));
  return screen.findByRole("dialog", { name: "Novo assistente" });
}

async function openEdit(user: User, name: string) {
  await user.click(screen.getByRole("button", { name: `Editar ${name}` }));
  return screen.findByRole("dialog", { name: "Editar assistente" });
}

async function pick(user: User, dialog: HTMLElement, field: string, option: string) {
  await user.click(within(dialog).getByRole("combobox", { name: field }));
  await user.click(await screen.findByRole("option", { name: option }));
}

describe("AssistantsPage list", () => {
  it("test_assistants_page_lists_assistants_with_status_and_provider", async () => {
    await renderAssistants();

    expect(screen.getByRole("heading", { level: 1, name: "Assistentes" })).toBeInTheDocument();
    const active = rowOf("Suporte ERP");
    expect(within(active).getByText("Dúvidas sobre o ERP.")).toBeInTheDocument();
    expect(within(active).getByText("OpenAI Produção · gpt-4.1-mini")).toBeInTheDocument();
    expect(within(active).getByText("Ativo")).toBeInTheDocument();
    const draft = rowOf("Rascunho");
    expect(within(draft).getByText("Anthropic · claude-sonnet")).toBeInTheDocument();
    expect(within(draft).getByText("Inativo")).toBeInTheDocument();
  });

  it("test_assistants_page_without_providers_points_to_providers", async () => {
    server.use(providersAs([]), assistantsAs([]));
    await renderAssistants();

    expect(screen.queryByRole("button", { name: "Novo assistente" })).not.toBeInTheDocument();
    expect(
      screen.getByText(/Cadastre um provedor de LLM antes de criar assistentes./),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Ir para provedores" })).toHaveAttribute(
      "href",
      `/w/${WORKSPACE_ID}/providers`,
    );
    expect(screen.getByText("Nenhum assistente cadastrado.")).toBeInTheDocument();
  });

  it("test_assistants_page_shows_model_alone_when_provider_is_not_listed", async () => {
    const user = userEvent.setup();
    server.use(providersAs([]), assistantsAs([makeAssistant()]));
    await renderAssistants();

    expect(within(rowOf("Suporte ERP")).getByText("gpt-4.1-mini")).toBeInTheDocument();
    const dialog = await openEdit(user, "Suporte ERP");
    expect(within(dialog).getByLabelText("Nome")).toHaveValue("Suporte ERP");
  });

  it("test_assistants_page_pages_long_lists", async () => {
    const user = userEvent.setup();
    const many = Array.from({ length: 22 }, (_, index) =>
      makeAssistant({
        id: `00000000-0000-4000-8000-${String(600 + index).padStart(12, "0")}`,
        name: `Assistente ${String(index).padStart(2, "0")}`,
      }),
    );
    server.use(assistantsAs(many));
    await renderAssistants();

    await user.click(screen.getByRole("button", { name: "Próxima" }));

    expect(screen.getByText("21–22 de 22")).toBeInTheDocument();
    expect(rowOf("Assistente 21")).toBeInTheDocument();
  });

  it("test_assistants_page_retries_after_load_failure", async () => {
    const user = userEvent.setup();
    server.use(assistantsServerError);
    renderWithProviders({ path: PATH });

    expect(await screen.findByText("Não foi possível carregar os assistentes.")).toHaveRole(
      "alert",
    );
    server.use(assistantsOk);
    await user.click(screen.getByRole("button", { name: "Tentar novamente" }));

    expect(await screen.findByRole("table", { name: TABLE })).toBeInTheDocument();
  });

  it("test_assistants_page_shows_loading_state", async () => {
    server.use(
      http.get("*/v1/workspaces/:workspaceId/assistants", async () => {
        await delay("infinite");
        return HttpResponse.json(null);
      }),
    );
    renderWithProviders({ path: PATH });

    expect(await screen.findByText("Carregando assistentes…")).toHaveRole("status");
  });

  it("test_assistants_page_renders_only_title_without_membership", async () => {
    renderWithProviders({
      routes: [{ path: "/w/:workspaceId/assistants", element: <AssistantsPage /> }],
      path: `/w/${OTHER_WORKSPACE_ID}/assistants`,
    });

    expect(
      await screen.findByRole("heading", { level: 1, name: "Assistentes" }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("test_assistants_page_viewer_cannot_edit", async () => {
    asRole("viewer");
    renderWithProviders({ path: PATH });

    expect(
      await screen.findByRole("heading", { level: 1, name: "Acesso negado" }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Editar/ })).not.toBeInTheDocument();
  });

  it("test_assistants_page_editor_manages_assistants", async () => {
    asRole("editor");
    await renderAssistants();

    expect(screen.getByRole("button", { name: "Novo assistente" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Editar Suporte ERP" })).toBeEnabled();
  });
});

describe("AssistantsPage create", () => {
  it("test_assistants_page_creates_assistant", async () => {
    const user = userEvent.setup();
    const store = assistantStore();
    server.use(...store.handlers);
    await renderAssistants();
    const dialog = await openCreate(user);

    expect(within(dialog).getByRole("combobox", { name: "Provedor" })).toHaveTextContent(
      "Anthropic",
    );
    expect(within(dialog).getByRole("checkbox", { name: "Ativo" })).toBeChecked();
    await user.type(within(dialog).getByLabelText("Nome"), "Financeiro");
    await user.type(within(dialog).getByLabelText("Descrição"), "Dúvidas de cobrança.");
    await user.type(within(dialog).getByLabelText("Prompt de sistema"), "Seja breve.");
    await pick(user, dialog, "Provedor", "OpenAI Produção");
    await user.type(within(dialog).getByLabelText("Modelo"), "gpt-4.1");
    const temperature = within(dialog).getByLabelText("Temperatura");
    await user.clear(temperature);
    await user.type(temperature, "0,5");
    const language = within(dialog).getByLabelText("Idioma");
    await user.clear(language);
    await user.type(language, "en");
    await pick(user, dialog, "Tom", "Formal");
    await user.click(within(dialog).getByRole("checkbox", { name: "Ativo" }));
    await user.click(within(dialog).getByRole("button", { name: "Salvar" }));

    expect(await screen.findByText("Assistente Financeiro criado.")).toHaveRole("status");
    expect(store.created).toEqual([
      {
        name: "Financeiro",
        description: "Dúvidas de cobrança.",
        system_prompt: "Seja breve.",
        provider_id: PROVIDER_ID,
        model: "gpt-4.1",
        temperature: 0.5,
        language: "en",
        tone: "formal",
        no_source_message: "",
        active: false,
      },
    ]);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await waitFor(() => {
      expect(within(rowOf("Financeiro")).getByText("Inativo")).toBeInTheDocument();
    });
  });

  it("test_assistants_page_validates_create_form", async () => {
    const user = userEvent.setup();
    const store = assistantStore();
    server.use(...store.handlers);
    await renderAssistants();
    const dialog = await openCreate(user);
    const temperature = within(dialog).getByLabelText("Temperatura");
    const language = within(dialog).getByLabelText("Idioma");

    await user.clear(temperature);
    await user.type(temperature, "3");
    await user.clear(language);
    await user.type(language, "português");
    await user.click(within(dialog).getByRole("button", { name: "Salvar" }));

    expect(await within(dialog).findByText("Informe o nome do assistente.")).toBeInTheDocument();
    expect(within(dialog).getByText("Informe o modelo.")).toBeInTheDocument();
    expect(within(dialog).getByText("Informe um número de 0 a 2.")).toBeInTheDocument();
    expect(
      within(dialog).getByText("Informe um código de idioma válido, como pt-BR."),
    ).toBeInTheDocument();

    await user.type(within(dialog).getByLabelText("Modelo"), "gpt 4");
    await user.click(within(dialog).getByRole("button", { name: "Salvar" }));

    expect(
      await within(dialog).findByText("O identificador do modelo não pode ter espaços."),
    ).toBeInTheDocument();
    expect(store.created).toEqual([]);
  });

  it("test_assistants_page_shows_name_taken_error", async () => {
    const user = userEvent.setup();
    const store = assistantStore();
    server.use(...store.handlers);
    await renderAssistants();
    const dialog = await openCreate(user);

    await user.type(within(dialog).getByLabelText("Nome"), "Rascunho");
    await user.type(within(dialog).getByLabelText("Modelo"), "gpt-4.1");
    await user.click(within(dialog).getByRole("button", { name: "Salvar" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent(
      "Já existe um assistente com este nome no workspace.",
    );
  });

  it("test_assistants_page_shows_provider_invalid_error", async () => {
    const user = userEvent.setup();
    await renderAssistants();
    server.use(createAssistantFails(422, "assistant_provider_invalid"));
    const dialog = await openCreate(user);

    await user.type(within(dialog).getByLabelText("Nome"), "Novo");
    await user.type(within(dialog).getByLabelText("Modelo"), "gpt-4.1");
    await user.click(within(dialog).getByRole("button", { name: "Salvar" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent(
      "Escolha um provedor de LLM cadastrado neste workspace.",
    );
  });

  it("test_assistants_page_disables_submit_while_saving", async () => {
    const user = userEvent.setup();
    await renderAssistants();
    server.use(
      http.post("*/v1/workspaces/:workspaceId/assistants", async () => {
        await delay("infinite");
        return HttpResponse.json(null);
      }),
    );
    const dialog = await openCreate(user);

    await user.type(within(dialog).getByLabelText("Nome"), "Novo");
    await user.type(within(dialog).getByLabelText("Modelo"), "gpt-4.1");
    await user.click(within(dialog).getByRole("button", { name: "Salvar" }));

    expect(await within(dialog).findByRole("button", { name: "Enviando…" })).toBeDisabled();
  });
});

describe("AssistantsPage edit", () => {
  it("test_assistants_page_edits_and_deactivates", async () => {
    const user = userEvent.setup();
    const store = assistantStore();
    server.use(...store.handlers);
    await renderAssistants();
    const dialog = await openEdit(user, "Suporte ERP");

    expect(within(dialog).getByLabelText("Prompt de sistema")).toHaveValue(
      "Responda com base nas fontes.",
    );
    expect(within(dialog).getByRole("combobox", { name: "Provedor" })).toHaveTextContent(
      "OpenAI Produção",
    );
    expect(within(dialog).getByLabelText("Temperatura")).toHaveValue("0.2");
    expect(within(dialog).getByRole("combobox", { name: "Tom" })).toHaveTextContent("Neutro");
    await user.clear(within(dialog).getByLabelText("Mensagem quando não há fonte"));
    await user.click(within(dialog).getByRole("checkbox", { name: "Ativo" }));
    await user.click(within(dialog).getByRole("button", { name: "Salvar" }));

    expect(await screen.findByText("Assistente Suporte ERP atualizado.")).toHaveRole("status");
    expect(store.changes).toEqual([
      {
        assistantId: ASSISTANT_ID,
        body: expect.objectContaining({
          provider_id: PROVIDER_ID,
          no_source_message: "",
          active: false,
        }) as unknown,
      },
    ]);
    await waitFor(() => {
      expect(within(rowOf("Suporte ERP")).getByText("Inativo")).toBeInTheDocument();
    });
    const reopened = await openEdit(user, "Suporte ERP");
    expect(within(reopened).getByLabelText("Mensagem quando não há fonte")).toHaveValue(
      DEFAULT_NO_SOURCE_MESSAGE,
    );
  });

  it("test_assistants_page_shows_update_error", async () => {
    const user = userEvent.setup();
    await renderAssistants();
    server.use(updateAssistantFails(403, "forbidden"));
    const dialog = await openEdit(user, "Rascunho");

    await user.click(within(dialog).getByRole("button", { name: "Salvar" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent(
      "Você não tem permissão para fazer isso.",
    );
  });
});

describe("AssistantsPage delete", () => {
  it("test_assistants_page_delete_warns_about_conversations", async () => {
    const user = userEvent.setup();
    const store = assistantStore();
    server.use(...store.handlers);
    await renderAssistants();

    await user.click(screen.getByRole("button", { name: "Excluir Rascunho" }));
    const dialog = await screen.findByRole("alertdialog", {
      name: "Excluir o assistente Rascunho?",
    });
    expect(dialog).toHaveAccessibleDescription(
      "As conversas deste assistente também serão excluídas, sem volta. Para manter o histórico, desative o assistente em vez de excluí-lo.",
    );
    await user.click(within(dialog).getByRole("button", { name: "Excluir" }));

    expect(await screen.findByText("O assistente Rascunho foi excluído.")).toHaveRole("status");
    expect(store.deleted).toEqual([OTHER_ASSISTANT_ID]);
    await waitFor(() => {
      expect(screen.queryByRole("button", { name: "Excluir Rascunho" })).not.toBeInTheDocument();
    });
  });

  it("test_assistants_page_shows_delete_error", async () => {
    const user = userEvent.setup();
    await renderAssistants();
    server.use(deleteAssistantFails(404, "not_found"));

    await user.click(screen.getByRole("button", { name: "Excluir Suporte ERP" }));
    await user.click(
      within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Excluir" }),
    );

    expect(await screen.findByRole("alert")).toHaveTextContent("O item procurado não existe.");
    expect(rowOf("Suporte ERP")).toBeInTheDocument();
  });
});
