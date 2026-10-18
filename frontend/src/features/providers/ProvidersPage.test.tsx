import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { delay, http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import type { Role } from "@/lib/api/auth";
import {
  makeMe,
  makeProvider,
  makeWorkspace,
  OTHER_PROVIDER_ID,
  OTHER_WORKSPACE_ID,
  PROVIDER_ID,
  WORKSPACE_ID,
} from "@/test/factories";
import {
  createProviderFails,
  deleteProviderFails,
  failedTest,
  meAs,
  providersAs,
  providersOk,
  providersRecorder,
  providersServerError,
  providerStore,
  testProviderFails,
} from "@/test/handlers";
import { renderWithProviders } from "@/test/renderWithProviders";
import { server } from "@/test/server";

import { ProvidersPage } from "./ProvidersPage";

const PATH = `/w/${WORKSPACE_ID}/providers`;
const TABLE = "Provedores de LLM";

type User = ReturnType<typeof userEvent.setup>;

function asRole(role: Role) {
  server.use(meAs(makeMe({ workspaces: [makeWorkspace({ role })] })));
}

async function renderProviders() {
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
  await user.click(screen.getByRole("button", { name: "Novo provedor" }));
  return screen.findByRole("dialog", { name: "Novo provedor" });
}

async function openEdit(user: User, name: string) {
  await user.click(screen.getByRole("button", { name: `Editar ${name}` }));
  return screen.findByRole("dialog", { name: "Editar provedor" });
}

describe("ProvidersPage list", () => {
  it("test_providers_page_lists_providers_with_masked_keys", async () => {
    server.use(
      providersAs([
        makeProvider({ id: OTHER_PROVIDER_ID, name: "Ollama", base_url: "http://ollama:11434/v1" }),
        makeProvider(),
      ]),
    );
    await renderProviders();

    expect(screen.getByRole("heading", { level: 1, name: "Provedores" })).toBeInTheDocument();
    const ollama = rowOf("Ollama");
    expect(within(ollama).getByText("http://ollama:11434/v1")).toBeInTheDocument();
    const openai = rowOf("OpenAI Produção");
    expect(within(openai).getByText("OpenAI")).toBeInTheDocument();
    expect(within(openai).getByText("Padrão do provedor")).toBeInTheDocument();
    expect(within(openai).getByText("****1234")).toBeInTheDocument();
  });

  it("test_providers_page_shows_empty_state", async () => {
    server.use(providersAs([]));
    await renderProviders();

    expect(
      screen.getByText(/Nenhum provedor cadastrado\. Comece por "Novo provedor"/),
    ).toBeInTheDocument();
  });

  it("test_providers_page_pages_long_lists", async () => {
    const user = userEvent.setup();
    const many = Array.from({ length: 25 }, (_, index) =>
      makeProvider({
        id: `00000000-0000-4000-8000-${String(500 + index).padStart(12, "0")}`,
        name: `Provedor ${String(index).padStart(2, "0")}`,
      }),
    );
    server.use(providersAs(many));
    await renderProviders();

    expect(screen.getByText("1–20 de 25")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Próxima" }));

    expect(await screen.findByText("21–25 de 25")).toBeInTheDocument();
    expect(rowOf("Provedor 24")).toBeInTheDocument();
  });

  it("test_providers_page_retries_after_load_failure", async () => {
    const user = userEvent.setup();
    server.use(providersServerError);
    renderWithProviders({ path: PATH });

    expect(await screen.findByText("Não foi possível carregar os provedores.")).toHaveRole("alert");
    server.use(providersOk);
    await user.click(screen.getByRole("button", { name: "Tentar novamente" }));

    expect(await screen.findByRole("table", { name: TABLE })).toBeInTheDocument();
  });

  it("test_providers_page_shows_loading_state", async () => {
    server.use(
      http.get("*/v1/workspaces/:workspaceId/providers", async () => {
        await delay("infinite");
        return HttpResponse.json(null);
      }),
    );
    renderWithProviders({ path: PATH });

    expect(await screen.findByText("Carregando provedores…")).toHaveRole("status");
  });

  it("test_providers_page_renders_only_title_without_membership", async () => {
    renderWithProviders({
      routes: [{ path: "/w/:workspaceId/providers", element: <ProvidersPage /> }],
      path: `/w/${OTHER_WORKSPACE_ID}/providers`,
    });

    expect(
      await screen.findByRole("heading", { level: 1, name: "Provedores" }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Novo provedor" })).not.toBeInTheDocument();
  });

  it("test_providers_page_viewer_gets_forbidden", async () => {
    asRole("viewer");
    renderWithProviders({ path: PATH });

    expect(
      await screen.findByRole("heading", { level: 1, name: "Acesso negado" }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Provedores" })).not.toBeInTheDocument();
  });

  it("test_providers_page_editor_manages_providers", async () => {
    asRole("editor");
    await renderProviders();

    expect(screen.getByRole("button", { name: "Novo provedor" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Excluir Anthropic" })).toBeEnabled();
  });
});

describe("ProvidersPage search, filter and sort", () => {
  async function choose(user: User, label: string, option: string) {
    await user.click(screen.getByRole("combobox", { name: label }));
    await user.click(await screen.findByRole("option", { name: option }));
  }

  it("test_providers_page_searches_by_name_on_the_api", async () => {
    const user = userEvent.setup();
    const recorder = providersRecorder();
    server.use(recorder.handler);
    const { router } = await renderProviders();

    await user.type(screen.getByRole("searchbox", { name: "Buscar provedores" }), "open");

    await waitFor(() => {
      expect(recorder.last()).toBe("query=open&sort=name");
    });
    await waitFor(() => {
      expect(screen.queryByText("Anthropic")).not.toBeInTheDocument();
    });
    expect(rowOf("OpenAI Produção")).toBeInTheDocument();
    expect(router.state.location.search).toBe("?q=open");
  });

  it("test_providers_page_filters_by_kind_and_clears", async () => {
    const user = userEvent.setup();
    const recorder = providersRecorder();
    server.use(recorder.handler);
    const { router } = await renderProviders();

    await choose(user, "Tipo", "Anthropic");

    await waitFor(() => {
      expect(recorder.last()).toBe("kind=anthropic&sort=name");
    });
    expect(router.state.location.search).toBe("?kind=anthropic");
    await user.click(screen.getByRole("button", { name: "Limpar filtros" }));
    await waitFor(() => {
      expect(router.state.location.search).toBe("");
    });
    expect(screen.queryByRole("button", { name: "Limpar filtros" })).not.toBeInTheDocument();
  });

  it("test_providers_page_sorts_and_goes_back_to_page_one", async () => {
    const user = userEvent.setup();
    const recorder = providersRecorder();
    server.use(recorder.handler);
    const { router } = renderWithProviders({ path: `${PATH}?offset=20` });
    await screen.findByRole("table", { name: TABLE });

    await choose(user, "Ordenar por", "Mais recentes primeiro");

    await waitFor(() => {
      expect(recorder.last()).toBe("sort=-created_at");
    });
    expect(recorder.queries.at(-1)?.get("offset")).toBe("0");
    expect(router.state.location.search).toBe("?sort=-created_at");
  });

  it("test_providers_page_link_past_the_end_goes_to_the_last_page", async () => {
    const recorder = providersRecorder();
    server.use(recorder.handler);
    const { router } = renderWithProviders({ path: `${PATH}?offset=40` });

    expect(await screen.findByText("1–2 de 2")).toBeInTheDocument();
    expect(router.state.location.search).toBe("");
    await waitFor(() => {
      expect(rowOf("Anthropic")).toBeInTheDocument();
    });
    expect(recorder.queries.map((query) => query.get("offset"))).toEqual(["40", "0"]);
  });

  it("test_providers_page_opens_a_shared_filtered_link", async () => {
    const recorder = providersRecorder([]);
    server.use(recorder.handler);
    renderWithProviders({ path: `${PATH}?q=nada&kind=openai&sort=-name` });

    expect(
      await screen.findByText("Nada encontrado com a busca e os filtros atuais."),
    ).toBeVisible();
    expect(recorder.last()).toBe("kind=openai&query=nada&sort=-name");
    expect(screen.getByRole("searchbox", { name: "Buscar provedores" })).toHaveValue("nada");
    expect(screen.getByRole("combobox", { name: "Tipo" })).toHaveTextContent("OpenAI");
  });
});

describe("ProvidersPage create", () => {
  it("test_providers_page_creates_provider_and_never_shows_the_key", async () => {
    const user = userEvent.setup();
    const store = providerStore();
    server.use(...store.handlers);
    await renderProviders();
    const dialog = await openCreate(user);

    expect(within(dialog).getByRole("combobox", { name: "Tipo" })).toHaveTextContent("OpenAI");
    await user.click(within(dialog).getByRole("combobox", { name: "Tipo" }));
    await user.click(await screen.findByRole("option", { name: "OpenRouter" }));
    await user.type(within(dialog).getByLabelText("Nome"), " Roteador ");
    await user.type(within(dialog).getByLabelText("Chave de API"), "sk-secret-abcd");
    await user.click(within(dialog).getByRole("button", { name: "Salvar" }));

    expect(await screen.findByText("Provedor Roteador cadastrado.")).toHaveRole("status");
    expect(store.created).toEqual([
      { kind: "openrouter", name: "Roteador", api_key: "sk-secret-abcd" },
    ]);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await waitFor(() => {
      expect(within(rowOf("Roteador")).getByText("****abcd")).toBeInTheDocument();
    });
    expect(document.body).not.toHaveTextContent("sk-secret-abcd");

    const reopened = await openCreate(user);
    expect(within(reopened).getByLabelText("Chave de API")).toHaveValue("");
  });

  it("test_providers_page_sends_base_url_when_given", async () => {
    const user = userEvent.setup();
    const store = providerStore();
    server.use(...store.handlers);
    await renderProviders();
    const dialog = await openCreate(user);

    await user.type(within(dialog).getByLabelText("Nome"), "Ollama");
    await user.type(within(dialog).getByLabelText("URL base (opcional)"), "http://ollama:11434/v1");
    await user.type(within(dialog).getByLabelText("Chave de API"), "ollama-local");
    await user.click(within(dialog).getByRole("button", { name: "Salvar" }));

    await screen.findByText("Provedor Ollama cadastrado.");
    expect(store.created).toEqual([
      {
        kind: "openai",
        name: "Ollama",
        base_url: "http://ollama:11434/v1",
        api_key: "ollama-local",
      },
    ]);
  });

  it("test_providers_page_validates_create_form", async () => {
    const user = userEvent.setup();
    const store = providerStore();
    server.use(...store.handlers);
    await renderProviders();
    const dialog = await openCreate(user);

    await user.click(within(dialog).getByRole("button", { name: "Salvar" }));
    expect(await within(dialog).findByText("Informe o nome do provedor.")).toBeInTheDocument();
    expect(within(dialog).getByText("Informe a chave de API.")).toBeInTheDocument();

    await user.type(within(dialog).getByLabelText("Nome"), "Novo");
    await user.type(within(dialog).getByLabelText("URL base (opcional)"), "ftp://x");
    await user.type(within(dialog).getByLabelText("Chave de API"), "curta");
    await user.click(within(dialog).getByRole("button", { name: "Salvar" }));

    expect(
      await within(dialog).findByText("Informe uma URL que comece com http:// ou https://."),
    ).toBeInTheDocument();
    expect(
      within(dialog).getByText("A chave de API precisa ter ao menos 8 caracteres."),
    ).toBeInTheDocument();
    expect(store.created).toEqual([]);
  });

  it("test_providers_page_shows_name_taken_error", async () => {
    const user = userEvent.setup();
    const store = providerStore();
    server.use(...store.handlers);
    await renderProviders();
    const dialog = await openCreate(user);

    await user.type(within(dialog).getByLabelText("Nome"), "Anthropic");
    await user.type(within(dialog).getByLabelText("Chave de API"), "sk-12345678");
    await user.click(within(dialog).getByRole("button", { name: "Salvar" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent(
      "Já existe um provedor com este nome no workspace.",
    );
  });

  it("test_providers_page_shows_kind_not_allowed_error", async () => {
    const user = userEvent.setup();
    await renderProviders();
    server.use(createProviderFails(422, "provider_kind_not_allowed"));
    const dialog = await openCreate(user);

    await user.click(within(dialog).getByRole("combobox", { name: "Tipo" }));
    await user.click(await screen.findByRole("option", { name: "Fake (testes, sem rede)" }));
    await user.type(within(dialog).getByLabelText("Nome"), "Teste");
    await user.type(within(dialog).getByLabelText("Chave de API"), "fake-key-123");
    await user.click(within(dialog).getByRole("button", { name: "Salvar" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent(
      "Este tipo de provedor não é permitido nesta instalação.",
    );
  });

  it("test_providers_page_disables_submit_while_saving", async () => {
    const user = userEvent.setup();
    await renderProviders();
    server.use(
      http.post("*/v1/workspaces/:workspaceId/providers", async () => {
        await delay("infinite");
        return HttpResponse.json(null);
      }),
    );
    const dialog = await openCreate(user);

    await user.type(within(dialog).getByLabelText("Nome"), "Novo");
    await user.type(within(dialog).getByLabelText("Chave de API"), "sk-12345678");
    await user.click(within(dialog).getByRole("button", { name: "Salvar" }));

    expect(await within(dialog).findByRole("button", { name: "Enviando…" })).toBeDisabled();
  });

  it("test_providers_page_cancel_discards_typed_key", async () => {
    const user = userEvent.setup();
    await renderProviders();
    const dialog = await openCreate(user);

    await user.type(within(dialog).getByLabelText("Chave de API"), "sk-abandoned");
    await user.click(within(dialog).getByRole("button", { name: "Cancelar" }));
    const reopened = await openCreate(user);

    expect(within(reopened).getByLabelText("Chave de API")).toHaveValue("");
  });
});

describe("ProvidersPage edit", () => {
  it("test_providers_page_edit_without_key_keeps_the_stored_one", async () => {
    const user = userEvent.setup();
    const store = providerStore();
    server.use(...store.handlers);
    await renderProviders();
    const dialog = await openEdit(user, "OpenAI Produção");

    expect(within(dialog).getByRole("combobox", { name: "Tipo" })).toBeDisabled();
    expect(within(dialog).getByText("O tipo não muda depois do cadastro.")).toBeInTheDocument();
    const key = within(dialog).getByLabelText("Nova chave de API (opcional)");
    expect(key).toHaveValue("");
    expect(key).toHaveAccessibleDescription("Chave atual: ****1234. Deixe em branco para manter.");
    const name = within(dialog).getByLabelText("Nome");
    await user.clear(name);
    await user.type(name, "OpenAI Principal");
    await user.click(within(dialog).getByRole("button", { name: "Salvar" }));

    expect(await screen.findByText("Provedor OpenAI Principal atualizado.")).toHaveRole("status");
    expect(store.changes).toEqual([
      { providerId: PROVIDER_ID, body: { name: "OpenAI Principal", base_url: null } },
    ]);
    await waitFor(() => {
      expect(within(rowOf("OpenAI Principal")).getByText("****1234")).toBeInTheDocument();
    });
  });

  it("test_providers_page_edit_replaces_key_and_base_url", async () => {
    const user = userEvent.setup();
    const store = providerStore();
    server.use(...store.handlers);
    await renderProviders();
    const dialog = await openEdit(user, "Anthropic");

    await user.type(within(dialog).getByLabelText("URL base (opcional)"), "https://proxy.test/v1");
    await user.type(
      within(dialog).getByLabelText("Nova chave de API (opcional)"),
      "sk-ant-new-9876",
    );
    await user.click(within(dialog).getByRole("button", { name: "Salvar" }));

    await screen.findByText("Provedor Anthropic atualizado.");
    expect(store.changes).toEqual([
      {
        providerId: OTHER_PROVIDER_ID,
        body: { name: "Anthropic", base_url: "https://proxy.test/v1", api_key: "sk-ant-new-9876" },
      },
    ]);
    await waitFor(() => {
      expect(within(rowOf("Anthropic")).getByText("****9876")).toBeInTheDocument();
    });
    expect(document.body).not.toHaveTextContent("sk-ant-new-9876");
  });

  it("test_providers_page_edit_rejects_short_new_key", async () => {
    const user = userEvent.setup();
    const store = providerStore();
    server.use(...store.handlers);
    await renderProviders();
    const dialog = await openEdit(user, "Anthropic");

    await user.type(within(dialog).getByLabelText("Nova chave de API (opcional)"), "abc");
    await user.click(within(dialog).getByRole("button", { name: "Salvar" }));

    expect(
      await within(dialog).findByText("A chave de API precisa ter ao menos 8 caracteres."),
    ).toBeInTheDocument();
    expect(store.changes).toEqual([]);
  });
});

describe("ProvidersPage connection test", () => {
  it("test_providers_page_reports_successful_connection", async () => {
    const user = userEvent.setup();
    const store = providerStore();
    server.use(...store.handlers);
    await renderProviders();

    await user.click(screen.getByRole("button", { name: "Testar a conexão com OpenAI Produção" }));

    // Next to the button, in its row, announced; the message on top says it again, quietly.
    const result = await within(rowOf("OpenAI Produção")).findByRole("status");
    expect(result).toHaveTextContent("Conexão funcionando.");
    expect(result).toHaveClass("text-success");
    const top = screen.getByText("Conexão com OpenAI Produção funcionando.");
    expect(top).not.toHaveRole("status");
    expect(top).toHaveClass("text-success");
    expect(store.tested).toEqual([PROVIDER_ID]);
  });

  it("test_providers_page_clears_the_result_when_testing_again", async () => {
    const user = userEvent.setup();
    const store = providerStore(undefined, {
      testResults: { [OTHER_PROVIDER_ID]: failedTest("provider_auth_failed") },
    });
    server.use(...store.handlers);
    await renderProviders();
    await user.click(screen.getByRole("button", { name: "Testar a conexão com OpenAI Produção" }));
    expect(await within(rowOf("OpenAI Produção")).findByRole("status")).toBeVisible();

    await user.click(screen.getByRole("button", { name: "Testar a conexão com Anthropic" }));

    const alert = await within(rowOf("Anthropic")).findByRole("alert");
    expect(alert).toHaveTextContent("O provedor de LLM recusou a chave de API.");
    expect(within(rowOf("OpenAI Produção")).queryByRole("status")).not.toBeInTheDocument();
    expect(screen.queryByText("Conexão com OpenAI Produção funcionando.")).not.toBeInTheDocument();
  });

  it.each([
    ["provider_auth_failed", "O provedor de LLM recusou a chave de API. Confira a credencial."],
    [
      "provider_rate_limited",
      "O provedor de LLM atingiu o limite de uso. Aguarde um pouco e tente de novo.",
    ],
    [
      "provider_unavailable",
      "O provedor de LLM está indisponível no momento. Tente de novo em instantes.",
    ],
    [
      "provider_request_failed",
      "O provedor de LLM recusou o pedido. Confira a URL base do provedor e o modelo configurado no assistente.",
    ],
    ["something_new", "Algo deu errado. Tente novamente."],
  ])("test_providers_page_reports_failed_connection_%s", async (code, reason) => {
    const user = userEvent.setup();
    const store = providerStore(undefined, { testResults: { [PROVIDER_ID]: failedTest(code) } });
    server.use(...store.handlers);
    await renderProviders();

    const button = screen.getByRole("button", { name: "Testar a conexão com OpenAI Produção" });
    await user.click(button);

    const alert = await within(rowOf("OpenAI Produção")).findByRole("alert");
    expect(alert).toHaveTextContent(reason);
    expect(alert).toHaveClass("text-destructive");
    expect(screen.getAllByRole("alert")).toHaveLength(1);
    expect(screen.getByText(`A conexão com OpenAI Produção falhou: ${reason}`)).toBeVisible();
    // The focus stays on the button: the result next to it is announced.
    expect(button).toHaveFocus();
  });

  it("test_providers_page_shows_api_error_of_connection_test", async () => {
    const user = userEvent.setup();
    await renderProviders();
    server.use(testProviderFails(403, "forbidden"));

    await user.click(screen.getByRole("button", { name: "Testar a conexão com Anthropic" }));

    expect(await within(rowOf("Anthropic")).findByRole("alert")).toHaveTextContent(
      "Você não tem permissão para fazer isso.",
    );
  });

  it("test_providers_page_marks_provider_under_test", async () => {
    const user = userEvent.setup();
    await renderProviders();
    server.use(
      http.post("*/v1/workspaces/:workspaceId/providers/:providerId/test", async () => {
        await delay("infinite");
        return HttpResponse.json(null);
      }),
    );

    await user.click(screen.getByRole("button", { name: "Testar a conexão com Anthropic" }));

    const testing = await screen.findByRole("button", { name: "Testar a conexão com Anthropic" });
    expect(testing).toHaveTextContent("Testando…");
    expect(testing).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "Testar a conexão com OpenAI Produção" }),
    ).toHaveTextContent("Testar conexão");
  });
});

describe("ProvidersPage delete", () => {
  it("test_providers_page_deletes_after_confirmation", async () => {
    const user = userEvent.setup();
    const store = providerStore();
    server.use(...store.handlers);
    await renderProviders();

    await user.click(screen.getByRole("button", { name: "Excluir Anthropic" }));
    const dialog = await screen.findByRole("alertdialog", {
      name: "Excluir o provedor Anthropic?",
    });
    await user.click(within(dialog).getByRole("button", { name: "Excluir" }));

    expect(await screen.findByText("O provedor Anthropic foi excluído.")).toHaveRole("status");
    expect(store.deleted).toEqual([OTHER_PROVIDER_ID]);
    await waitFor(() => {
      expect(screen.queryByRole("button", { name: "Excluir Anthropic" })).not.toBeInTheDocument();
    });
  });

  it("test_providers_page_explains_provider_in_use", async () => {
    const user = userEvent.setup();
    const store = providerStore(undefined, { inUse: [PROVIDER_ID] });
    server.use(...store.handlers);
    await renderProviders();

    await user.click(screen.getByRole("button", { name: "Excluir OpenAI Produção" }));
    await user.click(
      within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Excluir" }),
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Esta credencial está em uso por uma coleção ou por um nível de resposta. Troque a credencial onde ela é usada antes de excluí-la.",
    );
    expect(store.deleted).toEqual([]);
    expect(rowOf("OpenAI Produção")).toBeInTheDocument();
  });

  it("test_providers_page_cancel_keeps_provider", async () => {
    const user = userEvent.setup();
    await renderProviders();
    server.use(deleteProviderFails(500, "internal_error"));

    await user.click(screen.getByRole("button", { name: "Excluir Anthropic" }));
    await user.click(
      within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Cancelar" }),
    );

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(rowOf("Anthropic")).toBeInTheDocument();
  });
});
