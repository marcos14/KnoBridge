import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { Role } from "@/lib/api/auth";
import {
  COLLECTION_ID,
  makeCollection,
  makeMe,
  makeProvider,
  makeProviders,
  makeWorkspace,
  OTHER_COLLECTION_ID,
  OTHER_PROVIDER_ID,
  OTHER_WORKSPACE_ID,
  PROVIDER_ID,
  WORKSPACE_ID,
} from "@/test/factories";
import {
  collectionsAs,
  collectionsServerError,
  collectionStore,
  createCollectionFails,
  meAs,
  pendingPost,
  providersAs,
  providersServerError,
} from "@/test/handlers";
import { renderWithProviders } from "@/test/renderWithProviders";
import { server } from "@/test/server";

import { CollectionsPage } from "./CollectionsPage";

const PATH = `/w/${WORKSPACE_ID}/collections`;
const TABLE = "Coleções do workspace";

type User = ReturnType<typeof userEvent.setup>;

function asRole(role: Role) {
  server.use(meAs(makeMe({ workspaces: [makeWorkspace({ role })] })));
}

async function renderCollections() {
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
  await user.click(screen.getByRole("button", { name: "Nova coleção" }));
  return screen.findByRole("dialog", { name: "Nova coleção" });
}

async function openEdit(user: User, name: string) {
  await user.click(screen.getByRole("button", { name: `Editar ${name}` }));
  return screen.findByRole("dialog", { name: "Editar coleção" });
}

describe("CollectionsPage list", () => {
  it("test_collections_page_lists_collections_with_counts", async () => {
    await renderCollections();

    expect(screen.getByRole("heading", { level: 1, name: "Coleções" })).toBeInTheDocument();
    const erp = rowOf("Código ERP");
    expect(within(erp).getByRole("link", { name: "Código ERP" })).toHaveAttribute(
      "href",
      `${PATH}/${COLLECTION_ID}`,
    );
    expect(within(erp).getByText("Repositório do ERP e seus commits.")).toBeInTheDocument();
    expect(within(erp).getByText("OpenAI Produção · text-embedding-3-small")).toBeInTheDocument();
    expect(within(erp).getByText("310")).toBeInTheDocument();
    expect(within(erp).getByText("42")).toBeInTheDocument();
  });

  it("test_collections_page_without_embedding_provider_points_to_providers", async () => {
    server.use(
      providersAs([makeProvider({ id: OTHER_PROVIDER_ID, kind: "anthropic" })]),
      ...collectionsAs([]),
    );
    await renderCollections();

    expect(screen.queryByRole("button", { name: "Nova coleção" })).not.toBeInTheDocument();
    expect(screen.getByText(/a Anthropic não oferece embeddings/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Ir para provedores" })).toHaveAttribute(
      "href",
      `/w/${WORKSPACE_ID}/providers`,
    );
    expect(screen.getByText("Nenhuma coleção cadastrada.")).toBeInTheDocument();
  });

  it("test_collections_page_pages_long_lists", async () => {
    const user = userEvent.setup();
    const many = Array.from({ length: 22 }, (_, index) =>
      makeCollection({
        id: `00000000-0000-4000-8000-${String(700 + index).padStart(12, "0")}`,
        name: `Coleção ${String(index).padStart(2, "0")}`,
      }),
    );
    server.use(...collectionsAs(many));
    await renderCollections();

    await user.click(screen.getByRole("button", { name: "Próxima" }));

    expect(screen.getByText("21–22 de 22")).toBeInTheDocument();
    expect(rowOf("Coleção 21")).toBeInTheDocument();
  });

  it("test_collections_page_retries_after_load_failure", async () => {
    const user = userEvent.setup();
    server.use(collectionsServerError);
    renderWithProviders({ path: PATH });

    expect(await screen.findByText("Não foi possível carregar as coleções.")).toHaveRole("alert");
    server.use(...collectionsAs());
    await user.click(screen.getByRole("button", { name: "Tentar novamente" }));

    expect(await screen.findByRole("table", { name: TABLE })).toBeInTheDocument();
  });

  it("test_collections_page_shows_failure_of_provider_list", async () => {
    server.use(providersServerError);
    renderWithProviders({ path: PATH });

    expect(await screen.findByText("Não foi possível carregar as coleções.")).toHaveRole("alert");
  });

  it("test_collections_page_viewer_reads_without_actions_or_providers", async () => {
    asRole("viewer");
    server.use(providersServerError);
    await renderCollections();

    expect(within(rowOf("Código ERP")).getByText("text-embedding-3-small")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Nova coleção" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Editar/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Excluir/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("columnheader", { name: "Ações" })).not.toBeInTheDocument();
    expect(screen.queryByText(/Ir para provedores/)).not.toBeInTheDocument();
  });

  it("test_collections_page_viewer_retries_only_collections", async () => {
    const user = userEvent.setup();
    asRole("viewer");
    server.use(collectionsServerError);
    renderWithProviders({ path: PATH });

    await screen.findByText("Não foi possível carregar as coleções.");
    server.use(...collectionsAs());
    await user.click(screen.getByRole("button", { name: "Tentar novamente" }));

    expect(await screen.findByRole("table", { name: TABLE })).toBeInTheDocument();
  });

  it("test_collections_page_renders_title_outside_a_membership", async () => {
    renderWithProviders({
      path: `/w/${OTHER_WORKSPACE_ID}/collections`,
      routes: [{ path: "/w/:workspaceId/collections", element: <CollectionsPage /> }],
    });

    expect(await screen.findByRole("heading", { level: 1, name: "Coleções" })).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });
});

describe("CollectionsPage create", () => {
  it("test_create_collection_validates_and_saves_with_default_model", async () => {
    const user = userEvent.setup();
    const store = collectionStore([]);
    server.use(...store.handlers);
    await renderCollections();

    const dialog = await openCreate(user);
    expect(
      within(dialog).getByRole("combobox", { name: "Credencial de embedding" }),
    ).toHaveTextContent("OpenAI Produção");
    expect(within(dialog).getByLabelText("Modelo de embedding")).toHaveValue(
      "text-embedding-3-small",
    );
    await user.clear(within(dialog).getByLabelText("Modelo de embedding"));
    await user.type(within(dialog).getByLabelText("Modelo de embedding"), "modelo errado");
    await user.click(within(dialog).getByRole("button", { name: "Salvar" }));

    expect(await within(dialog).findByText("Informe o nome da coleção.")).toBeInTheDocument();
    expect(
      within(dialog).getByText("O identificador do modelo não pode ter espaços."),
    ).toBeInTheDocument();
    expect(store.created).toEqual([]);

    await user.type(within(dialog).getByLabelText("Nome"), "Chamados");
    await user.type(within(dialog).getByLabelText("Descrição"), "Tickets resolvidos");
    await user.clear(within(dialog).getByLabelText("Modelo de embedding"));
    await user.type(within(dialog).getByLabelText("Modelo de embedding"), "text-embedding-3-small");
    await user.click(within(dialog).getByRole("button", { name: "Salvar" }));

    expect(await screen.findByText("Coleção Chamados criada.")).toHaveRole("status");
    expect(store.created).toEqual([
      {
        name: "Chamados",
        description: "Tickets resolvidos",
        provider_id: PROVIDER_ID,
        embedding_model: "text-embedding-3-small",
      },
    ]);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(rowOf("Chamados")).toBeInTheDocument();
  });

  it("test_create_collection_offers_only_embedding_providers_and_swaps_model", async () => {
    const user = userEvent.setup();
    const openrouter = makeProvider({
      id: "00000000-0000-4000-8000-0000000000e3",
      name: "OpenRouter",
      kind: "openrouter",
    });
    server.use(providersAs([...makeProviders(), openrouter]));
    await renderCollections();

    const dialog = await openCreate(user);
    await user.click(within(dialog).getByRole("combobox", { name: "Credencial de embedding" }));

    expect(screen.queryByRole("option", { name: "Anthropic" })).not.toBeInTheDocument();
    await user.click(await screen.findByRole("option", { name: "OpenRouter" }));
    expect(within(dialog).getByLabelText("Modelo de embedding")).toHaveValue(
      "openai/text-embedding-3-small",
    );

    await user.clear(within(dialog).getByLabelText("Modelo de embedding"));
    await user.type(within(dialog).getByLabelText("Modelo de embedding"), "meu-modelo");
    await user.click(within(dialog).getByRole("combobox", { name: "Credencial de embedding" }));
    await user.click(await screen.findByRole("option", { name: "OpenAI Produção" }));
    expect(within(dialog).getByLabelText("Modelo de embedding")).toHaveValue("meu-modelo");
  });

  it("test_create_collection_shows_sending_state_and_cancels", async () => {
    const user = userEvent.setup();
    server.use(pendingPost("*/v1/workspaces/:workspaceId/collections"));
    await renderCollections();

    let dialog = await openCreate(user);
    await user.click(within(dialog).getByRole("button", { name: "Cancelar" }));
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
    dialog = await openCreate(user);
    await user.type(within(dialog).getByLabelText("Nome"), "Nova");
    await user.click(within(dialog).getByRole("button", { name: "Salvar" }));

    expect(await within(dialog).findByRole("button", { name: "Enviando…" })).toBeDisabled();
  });

  it("test_create_collection_shows_api_error", async () => {
    const user = userEvent.setup();
    server.use(createCollectionFails(422, "provider_embeddings_unsupported"));
    await renderCollections();

    const dialog = await openCreate(user);
    await user.type(within(dialog).getByLabelText("Nome"), "Nova");
    await user.click(within(dialog).getByRole("button", { name: "Salvar" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent(
      "Este provedor não oferece embeddings.",
    );
  });

  it("test_create_collection_with_taken_name_keeps_dialog_open", async () => {
    const user = userEvent.setup();
    server.use(...collectionStore().handlers);
    await renderCollections();

    const dialog = await openCreate(user);
    await user.type(within(dialog).getByLabelText("Nome"), "Manuais");
    await user.click(within(dialog).getByRole("button", { name: "Salvar" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent(
      "Já existe uma coleção com este nome no workspace.",
    );
  });
});

describe("CollectionsPage edit and delete", () => {
  it("test_edit_collection_with_documents_locks_provider_and_model", async () => {
    const user = userEvent.setup();
    const store = collectionStore();
    server.use(...store.handlers);
    await renderCollections();

    const dialog = await openEdit(user, "Código ERP");

    expect(within(dialog).getByText(/a credencial e o modelo não mudam mais/)).toBeInTheDocument();
    expect(
      within(dialog).getByRole("combobox", { name: "Credencial de embedding" }),
    ).toBeDisabled();
    expect(within(dialog).getByLabelText("Modelo de embedding")).toBeDisabled();
    await user.clear(within(dialog).getByLabelText("Nome"));
    await user.type(within(dialog).getByLabelText("Nome"), "Código do ERP");
    await user.click(within(dialog).getByRole("button", { name: "Salvar" }));

    expect(await screen.findByText("Coleção Código do ERP atualizada.")).toBeInTheDocument();
    expect(store.changes).toEqual([
      {
        collectionId: COLLECTION_ID,
        body: { name: "Código do ERP", description: "Repositório do ERP e seus commits." },
      },
    ]);
  });

  it("test_edit_empty_collection_sends_provider_and_model", async () => {
    const user = userEvent.setup();
    const store = collectionStore();
    server.use(...store.handlers);
    await renderCollections();

    const dialog = await openEdit(user, "Manuais");
    expect(within(dialog).getByLabelText("Modelo de embedding")).toBeEnabled();
    await user.clear(within(dialog).getByLabelText("Modelo de embedding"));
    await user.type(within(dialog).getByLabelText("Modelo de embedding"), "outro-modelo");
    await user.click(within(dialog).getByRole("button", { name: "Salvar" }));

    expect(await screen.findByText("Coleção Manuais atualizada.")).toBeInTheDocument();
    expect(store.changes).toEqual([
      {
        collectionId: OTHER_COLLECTION_ID,
        body: {
          name: "Manuais",
          description: "",
          provider_id: PROVIDER_ID,
          embedding_model: "outro-modelo",
        },
      },
    ]);
    expect(within(rowOf("Manuais")).getByText("OpenAI Produção · outro-modelo")).toBeVisible();
  });

  it("test_delete_collection_in_use_shows_reason", async () => {
    const user = userEvent.setup();
    const store = collectionStore();
    server.use(...store.handlers);
    await renderCollections();

    await user.click(screen.getByRole("button", { name: "Excluir Código ERP" }));
    const confirm = await screen.findByRole("alertdialog", {
      name: "Excluir a coleção Código ERP?",
    });
    await user.click(within(confirm).getByRole("button", { name: "Excluir" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "A coleção ainda tem fontes. Exclua as fontes antes de excluir a coleção.",
    );
    expect(store.deleted).toEqual([]);
    expect(rowOf("Código ERP")).toBeInTheDocument();
  });

  it("test_delete_empty_collection_removes_it", async () => {
    const user = userEvent.setup();
    const store = collectionStore();
    server.use(...store.handlers);
    await renderCollections();

    await user.click(screen.getByRole("button", { name: "Excluir Manuais" }));
    const confirm = await screen.findByRole("alertdialog");
    await user.click(within(confirm).getByRole("button", { name: "Excluir" }));

    expect(await screen.findByText("A coleção Manuais foi excluída.")).toHaveRole("status");
    expect(store.deleted).toEqual([OTHER_COLLECTION_ID]);
    await waitFor(() => {
      expect(screen.queryByText("Manuais")).not.toBeInTheDocument();
    });
  });
});
