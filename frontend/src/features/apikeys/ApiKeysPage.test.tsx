import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { delay, http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";

import type { Role } from "@/lib/api/auth";
import {
  API_KEY_ID,
  API_KEY_SECRET,
  makeApiKey,
  makeApiKeys,
  SCOPED_API_KEY_ID,
} from "@/test/apiKeyFactories";
import {
  ASSISTANT_ID,
  makeAssistant,
  makeMe,
  makeWorkspace,
  OTHER_ASSISTANT_ID,
  OTHER_WORKSPACE_ID,
  WORKSPACE_ID,
} from "@/test/factories";
import {
  apiKeyActionFails,
  apiKeysAs,
  apiKeysServerError,
  apiKeyStore,
  assistantsAs,
  assistantsServerError,
  meAs,
  pendingPost,
} from "@/test/handlers";
import { renderWithProviders } from "@/test/renderWithProviders";
import { server } from "@/test/server";

import { ApiKeysPage } from "./ApiKeysPage";

const PATH = `/w/${WORKSPACE_ID}/api-keys`;
const TABLE = "Chaves de API do workspace";
const ASSISTANTS = "*/v1/workspaces/:workspaceId/assistants";

type User = ReturnType<typeof userEvent.setup>;

function asRole(role: Role) {
  server.use(meAs(makeMe({ workspaces: [makeWorkspace({ role })] })));
}

async function renderApiKeys() {
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
  await user.click(screen.getByRole("button", { name: "Nova chave" }));
  return screen.findByRole("dialog", { name: "Nova chave de API" });
}

async function openEdit(user: User, name: string) {
  await user.click(screen.getByRole("button", { name: `Editar ${name}` }));
  return screen.findByRole("dialog", { name: `Editar a chave ${name}` });
}

async function chooseSelected(user: User, dialog: HTMLElement) {
  await user.click(within(dialog).getByRole("radio", { name: "Só os assistentes escolhidos" }));
}

describe("ApiKeysPage list", () => {
  it("test_api_keys_page_lists_prefix_scope_creation_last_use_and_state", async () => {
    await renderApiKeys();

    const portal = rowOf("portal-cliente");
    expect(within(portal).getByText("kbk_pc12ab34_…")).toBeInTheDocument();
    expect(within(portal).getByText("Todos os assistentes")).toBeInTheDocument();
    expect(within(portal).getByText("por Ana Teste")).toBeInTheDocument();
    expect(within(portal).getByText("há 1 hora")).toBeInTheDocument();
    expect(within(portal).getByText("Ativa")).toBeInTheDocument();

    const scoped = rowOf("integracao-erp");
    expect(within(scoped).getByText("Suporte ERP")).toBeInTheDocument();
    expect(within(scoped).getByText("Nunca usada")).toBeInTheDocument();
    expect(within(scoped).queryByText(/^por /)).not.toBeInTheDocument();

    const revoked = rowOf("antiga");
    expect(within(revoked).getByText("Revogada")).toBeInTheDocument();
    expect(within(revoked).queryByRole("button")).not.toBeInTheDocument();
  });

  it("test_api_keys_page_scope_without_the_assistants_list_shows_a_count", async () => {
    server.use(assistantsServerError);
    await renderApiKeys();

    expect(within(rowOf("integracao-erp")).getByText("1 assistente")).toBeInTheDocument();
  });

  it("test_api_keys_page_scope_of_deleted_assistants_says_none", async () => {
    server.use(
      apiKeysAs([makeApiKey({ assistant_ids: ["00000000-0000-4000-8000-00000000dead"] })]),
    );
    await renderApiKeys();

    expect(
      within(rowOf("portal-cliente")).getByText(
        "Nenhum assistente (os escolhidos foram excluídos)",
      ),
    ).toBeInTheDocument();
  });

  it("test_api_keys_page_shows_empty_list", async () => {
    server.use(apiKeysAs([]));
    await renderApiKeys();

    expect(
      screen.getByText("Nenhuma chave criada. Crie uma para chamar os assistentes pela API."),
    ).toBeInTheDocument();
  });

  it("test_api_keys_page_retries_after_load_failure", async () => {
    const user = userEvent.setup();
    server.use(apiKeysServerError);
    renderWithProviders({ path: PATH });

    expect(await screen.findByText("Carregando chaves…")).toHaveRole("status");
    expect(await screen.findByText("Não foi possível carregar as chaves.")).toHaveRole("alert");
    server.use(apiKeysAs());
    await user.click(screen.getByRole("button", { name: "Tentar novamente" }));

    expect(await screen.findByRole("table", { name: TABLE })).toBeInTheDocument();
  });

  it("test_api_keys_page_renders_title_outside_a_membership", async () => {
    renderWithProviders({
      path: `/w/${OTHER_WORKSPACE_ID}/api-keys`,
      routes: [{ path: "/w/:workspaceId/api-keys", element: <ApiKeysPage /> }],
    });

    expect(
      await screen.findByRole("heading", { level: 1, name: "Chaves de API" }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });
});

describe("ApiKeysPage roles", () => {
  it.each(["editor", "viewer"] as const)("test_api_keys_page_%s_gets_forbidden", async (role) => {
    asRole(role);
    renderWithProviders({ path: PATH });

    expect(
      await screen.findByRole("heading", { level: 1, name: "Acesso negado" }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Chaves de API" })).not.toBeInTheDocument();
  });

  it.each(["admin", "owner"] as const)("test_api_keys_page_%s_sees_the_menu_item", async (role) => {
    asRole(role);
    await renderApiKeys();

    expect(screen.getByRole("link", { name: "Chaves de API" })).toHaveAttribute("href", PATH);
    expect(screen.getByRole("button", { name: "Nova chave" })).toBeEnabled();
  });
});

describe("ApiKeysPage create", () => {
  it("test_create_api_key_shows_the_secret_once", async () => {
    const user = userEvent.setup();
    const store = apiKeyStore([]);
    server.use(...store.handlers);
    await renderApiKeys();

    let dialog = await openCreate(user);
    await user.click(within(dialog).getByRole("button", { name: "Salvar" }));
    expect(await within(dialog).findByText("Informe o nome da chave.")).toBeInTheDocument();
    expect(store.created).toEqual([]);

    await user.type(within(dialog).getByLabelText("Nome"), "  chatbot-site ");
    await user.click(within(dialog).getByRole("button", { name: "Salvar" }));

    dialog = await screen.findByRole("dialog", { name: "Chave chatbot-site criada" });
    expect(store.created).toEqual([{ name: "chatbot-site", assistant_ids: null }]);
    expect(within(dialog).getByText(API_KEY_SECRET)).toBeInTheDocument();
    expect(within(dialog).getByText(/variável de ambiente KNOBRIDGE_API_KEY/)).toBeInTheDocument();

    const secret = within(dialog).getByRole("region", { name: "Chave de API" });
    await user.click(within(secret).getByRole("button", { name: "Copiar chave" }));
    expect(await within(secret).findByRole("status")).toHaveTextContent("Copiado.");
    await expect(navigator.clipboard.readText()).resolves.toBe(API_KEY_SECRET);

    await user.click(within(dialog).getByRole("button", { name: "Concluído" }));
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
    expect(screen.queryByText(API_KEY_SECRET)).not.toBeInTheDocument();
    expect(within(rowOf("chatbot-site")).getByText("kbk_ab12cd34_…")).toBeInTheDocument();

    dialog = await openCreate(user);
    expect(within(dialog).getByLabelText("Nome")).toHaveValue("");
    expect(screen.queryByText(API_KEY_SECRET)).not.toBeInTheDocument();
  });

  it("test_create_api_key_with_chosen_assistants_sends_the_scope", async () => {
    const user = userEvent.setup();
    const store = apiKeyStore([]);
    server.use(...store.handlers);
    await renderApiKeys();

    const dialog = await openCreate(user);
    await user.type(within(dialog).getByLabelText("Nome"), "erp");
    await chooseSelected(user, dialog);
    const list = await within(dialog).findByRole("list", { name: "Assistentes da chave" });
    expect(within(list).getByLabelText("Rascunho (inativo)")).toBeInTheDocument();

    await user.click(within(dialog).getByRole("button", { name: "Salvar" }));
    expect(
      await within(dialog).findByText("Escolha pelo menos um assistente."),
    ).toBeInTheDocument();
    expect(store.created).toEqual([]);

    await user.click(within(list).getByLabelText("Suporte ERP"));
    await user.click(within(list).getByLabelText("Rascunho (inativo)"));
    await user.click(within(list).getByLabelText("Rascunho (inativo)"));
    await user.click(within(dialog).getByRole("button", { name: "Salvar" }));

    expect(await screen.findByRole("dialog", { name: "Chave erp criada" })).toBeInTheDocument();
    expect(store.created).toEqual([{ name: "erp", assistant_ids: [ASSISTANT_ID] }]);
  });

  it("test_create_api_key_with_taken_name_shows_the_error", async () => {
    const user = userEvent.setup();
    server.use(...apiKeyStore().handlers);
    await renderApiKeys();

    const dialog = await openCreate(user);
    await user.type(within(dialog).getByLabelText("Nome"), "portal-cliente");
    await user.click(within(dialog).getByRole("button", { name: "Salvar" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent(
      "Já existe uma chave de API com esse nome.",
    );
  });

  it("test_create_api_key_disables_submit_while_saving", async () => {
    const user = userEvent.setup();
    server.use(pendingPost("*/v1/workspaces/:workspaceId/api-keys"));
    await renderApiKeys();

    const dialog = await openCreate(user);
    await user.type(within(dialog).getByLabelText("Nome"), "chatbot");
    await user.click(within(dialog).getByRole("button", { name: "Salvar" }));

    expect(await within(dialog).findByRole("button", { name: "Enviando…" })).toBeDisabled();
  });

  it("test_create_api_key_scope_while_assistants_load", async () => {
    const user = userEvent.setup();
    server.use(
      http.get(ASSISTANTS, async () => {
        await delay("infinite");
        return HttpResponse.json(null);
      }),
    );
    await renderApiKeys();

    const dialog = await openCreate(user);
    await chooseSelected(user, dialog);

    expect(within(dialog).getByText("Carregando assistentes…")).toHaveRole("status");
  });

  it("test_create_api_key_scope_without_assistants", async () => {
    const user = userEvent.setup();
    server.use(assistantsAs([]));
    await renderApiKeys();

    const dialog = await openCreate(user);
    await chooseSelected(user, dialog);

    expect(within(dialog).getByText("Nenhum assistente no workspace.")).toBeInTheDocument();
  });
});

describe("ApiKeysPage edit", () => {
  it("test_edit_api_key_changes_name_and_scope", async () => {
    const user = userEvent.setup();
    const store = apiKeyStore();
    server.use(...store.handlers);
    await renderApiKeys();

    const dialog = await openEdit(user, "integracao-erp");
    expect(within(dialog).getByLabelText("Nome")).toHaveValue("integracao-erp");
    expect(
      within(dialog).getByRole("radio", { name: "Só os assistentes escolhidos" }),
    ).toBeChecked();
    expect(within(dialog).getByLabelText("Suporte ERP")).toBeChecked();

    await user.clear(within(dialog).getByLabelText("Nome"));
    await user.type(within(dialog).getByLabelText("Nome"), "erp");
    await user.click(within(dialog).getByLabelText("Rascunho (inativo)"));
    await user.click(within(dialog).getByRole("button", { name: "Salvar" }));

    expect(await screen.findByText("A chave erp foi salva.")).toHaveRole("status");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(store.changes).toEqual([
      {
        apiKeyId: SCOPED_API_KEY_ID,
        body: { name: "erp", assistant_ids: [ASSISTANT_ID, OTHER_ASSISTANT_ID] },
      },
    ]);
    await waitFor(() => {
      expect(within(rowOf("kbk_ie56cd78_")).getByText("Rascunho, Suporte ERP")).toBeInTheDocument();
    });
  });

  it("test_edit_api_key_back_to_every_assistant", async () => {
    const user = userEvent.setup();
    const store = apiKeyStore();
    server.use(...store.handlers);
    await renderApiKeys();

    const dialog = await openEdit(user, "integracao-erp");
    await user.click(
      within(dialog).getByRole("radio", {
        name: "Todos os assistentes ativos, inclusive os criados depois",
      }),
    );
    expect(within(dialog).queryByRole("list")).not.toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Salvar" }));

    expect(await screen.findByText("A chave integracao-erp foi salva.")).toBeInTheDocument();
    expect(store.changes).toEqual([{ apiKeyId: SCOPED_API_KEY_ID, body: { assistant_ids: null } }]);
  });

  it("test_edit_api_key_without_changes_sends_nothing", async () => {
    const user = userEvent.setup();
    const store = apiKeyStore();
    server.use(...store.handlers);
    await renderApiKeys();

    const dialog = await openEdit(user, "portal-cliente");
    await user.click(within(dialog).getByRole("button", { name: "Salvar" }));

    expect(await screen.findByText("A chave portal-cliente foi salva.")).toBeInTheDocument();
    expect(store.changes).toEqual([]);
  });

  it("test_edit_api_key_failure_keeps_the_dialog_with_the_error", async () => {
    const user = userEvent.setup();
    server.use(apiKeyActionFails("update", 409, "api_key_revoked"));
    await renderApiKeys();

    const dialog = await openEdit(user, "portal-cliente");
    await user.type(within(dialog).getByLabelText("Nome"), "-2");
    await user.click(within(dialog).getByRole("button", { name: "Salvar" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent(
      "Esta chave foi revogada e não pode mais ser alterada.",
    );
  });

  it("test_edit_api_key_scope_when_assistants_fail_to_load", async () => {
    const user = userEvent.setup();
    server.use(assistantsServerError);
    await renderApiKeys();

    const dialog = await openEdit(user, "integracao-erp");

    expect(await within(dialog).findByText("Não foi possível carregar os assistentes.")).toHaveRole(
      "alert",
    );
  });
});

describe("ApiKeysPage revoke", () => {
  it("test_revoke_api_key_after_confirmation", async () => {
    const user = userEvent.setup();
    const store = apiKeyStore();
    server.use(...store.handlers);
    await renderApiKeys();

    await user.click(screen.getByRole("button", { name: "Revogar portal-cliente" }));
    const confirm = await screen.findByRole("alertdialog", {
      name: "Revogar a chave portal-cliente?",
    });
    await user.click(within(confirm).getByRole("button", { name: "Revogar" }));

    expect(await screen.findByText("A chave portal-cliente foi revogada.")).toHaveRole("status");
    expect(store.revoked).toEqual([API_KEY_ID]);
    await waitFor(() => {
      expect(within(rowOf("portal-cliente")).getByText("Revogada")).toBeInTheDocument();
    });
    expect(
      screen.queryByRole("button", { name: "Revogar portal-cliente" }),
    ).not.toBeInTheDocument();
  });

  it("test_revoke_api_key_failure_shows_the_error", async () => {
    const user = userEvent.setup();
    server.use(apiKeyActionFails("revoke", 500, "internal_error"));
    await renderApiKeys();

    await user.click(screen.getByRole("button", { name: "Revogar portal-cliente" }));
    const confirm = await screen.findByRole("alertdialog");
    await user.click(within(confirm).getByRole("button", { name: "Revogar" }));

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(within(rowOf("portal-cliente")).getByText("Ativa")).toBeInTheDocument();
  });
});

describe("ApiKeysPage examples", () => {
  it("test_api_key_examples_use_this_server_and_the_first_active_assistant_without_the_key", async () => {
    const user = userEvent.setup();
    await renderApiKeys();

    const examples = screen.getByRole("region", { name: "Como usar" });
    expect(within(examples).getByText(/Exemplos com o assistente Suporte ERP/)).toBeInTheDocument();
    const curl = within(examples).getByRole("region", { name: "curl (API REST)" });
    expect(curl).toHaveTextContent(`${window.location.origin}/v1/conversations`);
    expect(curl).toHaveTextContent(ASSISTANT_ID);
    const python = within(examples).getByRole("region", {
      name: "Python (SDK oficial da OpenAI)",
    });
    expect(python).toHaveTextContent(`base_url="${window.location.origin}/v1"`);
    expect(python).toHaveTextContent('model="Suporte ERP"');
    const js = within(examples).getByRole("region", {
      name: "JavaScript (SDK oficial da OpenAI)",
    });
    expect(js).toHaveTextContent("answer.knobridge.citations");
    expect(examples).toHaveTextContent("KNOBRIDGE_API_KEY");
    expect(examples).not.toHaveTextContent("kbk_");

    await user.click(within(js).getByRole("button", { name: "Copiar exemplo JavaScript" }));
    await expect(navigator.clipboard.readText()).resolves.toMatch(/^import OpenAI from "openai";/);
  });

  it("test_api_key_examples_without_an_active_assistant_use_placeholders", async () => {
    server.use(assistantsAs([makeAssistant({ active: false })]));
    await renderApiKeys();

    const examples = screen.getByRole("region", { name: "Como usar" });
    expect(await within(examples).findByText(/Nenhum assistente ativo/)).toBeInTheDocument();
    expect(examples).toHaveTextContent('"assistant_id":"<id-do-assistente>"');
    expect(examples).toHaveTextContent('model="<nome do assistente>"');
  });

  it("test_api_key_examples_report_copy_failure", async () => {
    const user = userEvent.setup();
    await renderApiKeys();
    vi.spyOn(navigator.clipboard, "writeText").mockRejectedValueOnce(new Error("blocked"));

    const curl = screen.getByRole("region", { name: "curl (API REST)" });
    await user.click(within(curl).getByRole("button", { name: "Copiar exemplo curl" }));

    expect(await within(curl).findByRole("status")).toHaveTextContent(/copie/i);
  });
});

describe("ApiKeysPage defaults", () => {
  it("test_api_keys_default_handlers_list_the_default_keys", async () => {
    await renderApiKeys();

    expect(within(screen.getByRole("table", { name: TABLE })).getAllByRole("row")).toHaveLength(
      makeApiKeys().length + 1,
    );
  });
});
