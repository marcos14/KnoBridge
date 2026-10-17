import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { delay, http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import type { Role } from "@/lib/api/auth";
import {
  PRODUCT_ID,
  COLLECTION_ID,
  makeProduct,
  makeMe,
  makeWorkspace,
  OTHER_PRODUCT_ID,
  OTHER_COLLECTION_ID,
  OTHER_WORKSPACE_ID,
  WORKSPACE_ID,
} from "@/test/factories";
import {
  productsAs,
  productsOk,
  productsRecorder,
  productsServerError,
  productStore,
  collectionsAs,
  collectionsServerError,
  createProductFails,
  DEFAULT_NO_SOURCE_MESSAGE,
  deleteProductFails,
  duplicateProductFails,
  duplicateProductRecorder,
  meAs,
  providersAs,
  updateProductFails,
} from "@/test/handlers";
import { renderWithProviders } from "@/test/renderWithProviders";
import { server } from "@/test/server";

import { ProductsPage } from "./ProductsPage";

const PATH = `/w/${WORKSPACE_ID}/products`;
const TABLE = "Produtos do workspace";

type User = ReturnType<typeof userEvent.setup>;

function asRole(role: Role) {
  server.use(meAs(makeMe({ workspaces: [makeWorkspace({ role })] })));
}

async function renderProducts() {
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
  await user.click(screen.getByRole("button", { name: "Novo produto" }));
  return screen.findByRole("dialog", { name: "Novo produto" });
}

async function openEdit(user: User, name: string) {
  await user.click(screen.getByRole("button", { name: `Editar ${name}` }));
  return screen.findByRole("dialog", { name: "Editar produto" });
}

async function pick(user: User, dialog: HTMLElement, field: string, option: string) {
  await user.click(within(dialog).getByRole("combobox", { name: field }));
  await user.click(await screen.findByRole("option", { name: option }));
}

describe("ProductsPage list", () => {
  it("test_products_page_lists_products_with_status", async () => {
    await renderProducts();

    expect(screen.getByRole("heading", { level: 1, name: "Produtos" })).toBeInTheDocument();
    const active = rowOf("Suporte ERP");
    expect(within(active).getByText("Dúvidas sobre o ERP.")).toBeInTheDocument();
    expect(within(active).getByText("Ativo")).toBeInTheDocument();
    const draft = rowOf("Rascunho");
    expect(within(draft).getByText("Inativo")).toBeInTheDocument();
  });

  it("test_products_page_old_assistants_address_redirects", async () => {
    const { router } = renderWithProviders({ path: `/w/${WORKSPACE_ID}/assistants` });

    expect(await screen.findByRole("table", { name: TABLE })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe(PATH);
  });

  it("test_products_page_without_providers_points_to_providers", async () => {
    server.use(providersAs([]), productsAs([]));
    await renderProducts();

    expect(screen.queryByRole("button", { name: "Novo produto" })).not.toBeInTheDocument();
    expect(
      screen.getByText(
        /Cadastre um provedor de LLM e configure os níveis de resposta antes de criar produtos./,
      ),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Ir para provedores" })).toHaveAttribute(
      "href",
      `/w/${WORKSPACE_ID}/providers`,
    );
    expect(screen.getByText("Nenhum produto cadastrado.")).toBeInTheDocument();
  });

  it("test_products_page_edits_without_providers", async () => {
    const user = userEvent.setup();
    server.use(providersAs([]), productsAs([makeProduct()]));
    await renderProducts();

    const dialog = await openEdit(user, "Suporte ERP");
    expect(within(dialog).getByLabelText("Nome")).toHaveValue("Suporte ERP");
  });

  it("test_products_page_pages_long_lists", async () => {
    const user = userEvent.setup();
    const many = Array.from({ length: 22 }, (_, index) =>
      makeProduct({
        id: `00000000-0000-4000-8000-${String(600 + index).padStart(12, "0")}`,
        name: `Produto ${String(index).padStart(2, "0")}`,
      }),
    );
    server.use(productsAs(many));
    await renderProducts();

    await user.click(screen.getByRole("button", { name: "Próxima" }));

    expect(screen.getByText("21–22 de 22")).toBeInTheDocument();
    expect(rowOf("Produto 21")).toBeInTheDocument();
  });

  it("test_products_page_retries_after_load_failure", async () => {
    const user = userEvent.setup();
    server.use(productsServerError);
    renderWithProviders({ path: PATH });

    expect(await screen.findByText("Não foi possível carregar os produtos.")).toHaveRole("alert");
    server.use(productsOk);
    await user.click(screen.getByRole("button", { name: "Tentar novamente" }));

    expect(await screen.findByRole("table", { name: TABLE })).toBeInTheDocument();
  });

  it("test_products_page_shows_loading_state", async () => {
    server.use(
      http.get("*/v1/workspaces/:workspaceId/products", async () => {
        await delay("infinite");
        return HttpResponse.json(null);
      }),
    );
    renderWithProviders({ path: PATH });

    expect(await screen.findByText("Carregando produtos…")).toHaveRole("status");
  });

  it("test_products_page_renders_only_title_without_membership", async () => {
    renderWithProviders({
      routes: [{ path: "/w/:workspaceId/products", element: <ProductsPage /> }],
      path: `/w/${OTHER_WORKSPACE_ID}/products`,
    });

    expect(await screen.findByRole("heading", { level: 1, name: "Produtos" })).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("test_products_page_viewer_cannot_edit", async () => {
    asRole("viewer");
    renderWithProviders({ path: PATH });

    expect(
      await screen.findByRole("heading", { level: 1, name: "Acesso negado" }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Editar/ })).not.toBeInTheDocument();
  });

  it("test_products_page_editor_manages_products", async () => {
    asRole("editor");
    await renderProducts();

    expect(screen.getByRole("button", { name: "Novo produto" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Editar Suporte ERP" })).toBeEnabled();
  });
});

describe("ProductsPage search, filters and sort", () => {
  it("test_products_page_searches_filters_and_sorts_on_the_api", async () => {
    const user = userEvent.setup();
    const recorder = productsRecorder();
    server.use(recorder.handler);
    const { router } = await renderProducts();

    await user.type(screen.getByRole("searchbox", { name: "Buscar produtos" }), "suporte");
    await waitFor(() => {
      expect(recorder.last()).toBe("query=suporte&sort=name");
    });
    await waitFor(() => {
      expect(screen.queryByText("Rascunho")).not.toBeInTheDocument();
    });

    for (const [label, option] of [
      ["Status", "Ativos"],
      ["Coleções", "Código ERP"],
      ["Ordenar por", "Atualizados recentemente"],
    ] as const) {
      await user.click(screen.getByRole("combobox", { name: label }));
      await user.click(await screen.findByRole("option", { name: option }));
    }

    await waitFor(() => {
      expect(recorder.last()).toBe(
        `active=true&collection_id=${COLLECTION_ID}&query=suporte&sort=-updated_at`,
      );
    });
    expect(router.state.location.search).toBe(
      `?q=suporte&active=true&collection=${COLLECTION_ID}&sort=-updated_at`,
    );
  });

  it("test_products_page_empty_state_points_to_collections", async () => {
    server.use(productsAs([]));
    await renderProducts();

    expect(screen.getByText(/Crie um em "Novo produto"/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Ver coleções" })).toHaveAttribute(
      "href",
      `/w/${WORKSPACE_ID}/collections`,
    );
  });

  it("test_products_page_filtered_without_results_says_so", async () => {
    server.use(productsRecorder([]).handler);
    renderWithProviders({ path: `${PATH}?active=false` });

    expect(
      await screen.findByText("Nada encontrado com a busca e os filtros atuais."),
    ).toBeVisible();
    expect(screen.getByRole("button", { name: "Limpar filtros" })).toBeInTheDocument();
  });
});

describe("ProductsPage duplicate", () => {
  it("test_products_page_duplicates_and_opens_the_copy_for_editing", async () => {
    const user = userEvent.setup();
    const duplicate = duplicateProductRecorder();
    server.use(duplicate.handler);
    await renderProducts();

    await user.click(screen.getByRole("button", { name: "Duplicar Suporte ERP" }));

    const dialog = await screen.findByRole("dialog", { name: "Editar produto" });
    expect(within(dialog).getByLabelText("Nome")).toHaveValue("Suporte ERP (cópia)");
    expect(duplicate.requests).toEqual([{ productId: PRODUCT_ID, body: {} }]);
    expect(
      screen.getByText("Cópia criada: Suporte ERP (cópia). Ajuste o que precisar e salve."),
    ).toHaveRole("status");

    await user.click(within(dialog).getByRole("button", { name: "Salvar" }));

    expect(await screen.findByText("Produto Suporte ERP atualizado.")).toHaveRole("status");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("test_products_page_duplicate_dialog_can_be_dismissed", async () => {
    const user = userEvent.setup();
    await renderProducts();

    await user.click(screen.getByRole("button", { name: "Duplicar Rascunho" }));
    const dialog = await screen.findByRole("dialog", { name: "Editar produto" });
    await user.click(within(dialog).getByRole("button", { name: "Cancelar" }));

    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
  });

  it("test_products_page_duplicate_failure_shows_reason", async () => {
    const user = userEvent.setup();
    server.use(duplicateProductFails(403, "forbidden"));
    await renderProducts();

    await user.click(screen.getByRole("button", { name: "Duplicar Suporte ERP" }));

    expect(await screen.findByText("Você não tem permissão para fazer isso.")).toHaveRole("alert");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});

describe("ProductsPage create", () => {
  it("test_products_page_creates_product", async () => {
    const user = userEvent.setup();
    const store = productStore();
    server.use(...store.handlers);
    await renderProducts();
    const dialog = await openCreate(user);

    expect(within(dialog).queryByRole("combobox", { name: "Provedor" })).not.toBeInTheDocument();
    expect(within(dialog).queryByLabelText("Modelo")).not.toBeInTheDocument();
    expect(within(dialog).getByRole("checkbox", { name: "Ativo" })).toBeChecked();
    await user.type(within(dialog).getByLabelText("Nome"), "Financeiro");
    await user.type(within(dialog).getByLabelText("Descrição"), "Dúvidas de cobrança.");
    await user.type(within(dialog).getByLabelText("Texto extra"), "Seja breve.");
    const language = within(dialog).getByLabelText("Idioma");
    await user.clear(language);
    await user.type(language, "en");
    await pick(user, dialog, "Tom", "Formal");
    expect(
      within(dialog).getByText(
        "Nenhuma coleção selecionada: o produto responderá sempre sem fonte.",
      ),
    ).toBeVisible();
    await user.click(await within(dialog).findByRole("checkbox", { name: "Código ERP" }));
    expect(
      within(dialog).queryByText(
        "Nenhuma coleção selecionada: o produto responderá sempre sem fonte.",
      ),
    ).not.toBeInTheDocument();
    const minSimilarity = within(dialog).getByLabelText("Similaridade mínima");
    expect(minSimilarity).toHaveValue("");
    expect(minSimilarity).toHaveAccessibleDescription(
      /^De 0 a 1, ou em branco para usar o padrão do modelo de embedding de cada coleção\./,
    );
    await user.type(minSimilarity, "0,45");
    await user.click(within(dialog).getByRole("checkbox", { name: "Ativo" }));
    await user.click(within(dialog).getByRole("button", { name: "Salvar" }));

    expect(await screen.findByText("Produto Financeiro criado.")).toHaveRole("status");
    expect(store.created).toEqual([
      {
        name: "Financeiro",
        description: "Dúvidas de cobrança.",
        instructions: "Seja breve.",
        language: "en",
        tone: "formal",
        no_source_message: "",
        active: false,
        collection_ids: [COLLECTION_ID],
        min_similarity: 0.45,
        rerank: false,
        ticket_webhook_url: null,
      },
    ]);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await waitFor(() => {
      expect(within(rowOf("Financeiro")).getByText("Inativo")).toBeInTheDocument();
    });
  });

  it("test_products_page_validates_create_form", async () => {
    const user = userEvent.setup();
    const store = productStore();
    server.use(...store.handlers);
    await renderProducts();
    const dialog = await openCreate(user);
    const language = within(dialog).getByLabelText("Idioma");
    const minSimilarity = within(dialog).getByLabelText("Similaridade mínima");

    await user.clear(language);
    await user.type(language, "português");
    await user.clear(minSimilarity);
    await user.type(minSimilarity, "3");
    await user.click(within(dialog).getByRole("button", { name: "Salvar" }));

    expect(await within(dialog).findByText("Informe o nome do produto.")).toBeInTheDocument();
    expect(within(dialog).getByText("Informe um número de 0 a 1.")).toBeInTheDocument();
    expect(
      within(dialog).getByText("Informe um código de idioma válido, como pt-BR."),
    ).toBeInTheDocument();
    expect(store.created).toEqual([]);
  });

  it("test_products_page_shows_name_taken_error", async () => {
    const user = userEvent.setup();
    const store = productStore();
    server.use(...store.handlers);
    await renderProducts();
    const dialog = await openCreate(user);

    await user.type(within(dialog).getByLabelText("Nome"), "Rascunho");
    await user.click(within(dialog).getByRole("button", { name: "Salvar" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent(
      "Já existe um produto com este nome no workspace.",
    );
  });

  it("test_products_page_shows_level_not_configured_error", async () => {
    const user = userEvent.setup();
    await renderProducts();
    server.use(createProductFails(409, "level_not_configured"));
    const dialog = await openCreate(user);

    await user.type(within(dialog).getByLabelText("Nome"), "Novo");
    await user.click(within(dialog).getByRole("button", { name: "Salvar" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent(
      "Configure o provedor e o modelo de um nível de resposta antes de continuar.",
    );
  });

  it("test_products_page_disables_submit_while_saving", async () => {
    const user = userEvent.setup();
    await renderProducts();
    server.use(
      http.post("*/v1/workspaces/:workspaceId/products", async () => {
        await delay("infinite");
        return HttpResponse.json(null);
      }),
    );
    const dialog = await openCreate(user);

    await user.type(within(dialog).getByLabelText("Nome"), "Novo");
    await user.click(within(dialog).getByRole("button", { name: "Salvar" }));

    expect(await within(dialog).findByRole("button", { name: "Enviando…" })).toBeDisabled();
  });
});

describe("ProductsPage edit", () => {
  it("test_products_page_edits_and_deactivates", async () => {
    const user = userEvent.setup();
    const store = productStore();
    server.use(...store.handlers);
    await renderProducts();
    const dialog = await openEdit(user, "Suporte ERP");

    expect(within(dialog).getByLabelText("Texto extra")).toHaveValue(
      "Responda com base nas fontes.",
    );
    expect(within(dialog).getByRole("combobox", { name: "Tom" })).toHaveTextContent("Neutro");
    await user.clear(within(dialog).getByLabelText("Mensagem quando não há fonte"));
    await user.click(within(dialog).getByRole("checkbox", { name: "Ativo" }));
    await user.click(within(dialog).getByRole("button", { name: "Salvar" }));

    expect(await screen.findByText("Produto Suporte ERP atualizado.")).toHaveRole("status");
    expect(store.changes).toEqual([
      {
        productId: PRODUCT_ID,
        body: expect.objectContaining({
          instructions: "Responda com base nas fontes.",
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

  it("test_products_page_shows_update_error", async () => {
    const user = userEvent.setup();
    await renderProducts();
    server.use(updateProductFails(403, "forbidden"));
    const dialog = await openEdit(user, "Rascunho");

    await user.click(within(dialog).getByRole("button", { name: "Salvar" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent(
      "Você não tem permissão para fazer isso.",
    );
  });
});

describe("ProductsPage collections", () => {
  const NO_COLLECTION_WARNING =
    "Nenhuma coleção selecionada: o produto responderá sempre sem fonte.";

  it("test_products_page_lists_how_many_collections_each_uses", async () => {
    server.use(
      productsAs([
        makeProduct({ collection_ids: [COLLECTION_ID, OTHER_COLLECTION_ID] }),
        makeProduct({ id: OTHER_PRODUCT_ID, name: "Rascunho", collection_ids: [] }),
      ]),
    );
    await renderProducts();

    const header = screen.getByRole("columnheader", { name: "Coleções" });
    expect(header).toBeInTheDocument();
    expect(within(rowOf("Suporte ERP")).getByRole("cell", { name: "2" })).toBeInTheDocument();
    expect(within(rowOf("Rascunho")).getByText("Nenhuma (sem fonte)")).toBeInTheDocument();
  });

  it("test_products_page_edit_replaces_the_collection_set", async () => {
    const user = userEvent.setup();
    const store = productStore();
    server.use(...store.handlers);
    await renderProducts();
    const dialog = await openEdit(user, "Suporte ERP");

    const erp = await within(dialog).findByRole("checkbox", { name: "Código ERP" });
    const manuals = within(dialog).getByRole("checkbox", { name: "Manuais" });
    expect(erp).toBeChecked();
    expect(manuals).not.toBeChecked();
    expect(within(dialog).getByText("Repositório do ERP e seus commits.")).toBeVisible();
    expect(within(dialog).queryByText(NO_COLLECTION_WARNING)).not.toBeInTheDocument();
    await user.click(erp);
    expect(within(dialog).getByText(NO_COLLECTION_WARNING)).toBeVisible();
    await user.click(manuals);
    await user.click(within(dialog).getByRole("button", { name: "Salvar" }));

    expect(await screen.findByText("Produto Suporte ERP atualizado.")).toHaveRole("status");
    expect(store.changes).toEqual([
      {
        productId: PRODUCT_ID,
        body: expect.objectContaining({
          collection_ids: [OTHER_COLLECTION_ID],
          min_similarity: 0.35,
        }) as unknown,
      },
    ]);
  });

  it("test_products_page_can_save_without_collections", async () => {
    const user = userEvent.setup();
    const store = productStore();
    server.use(...store.handlers);
    await renderProducts();
    const dialog = await openEdit(user, "Suporte ERP");

    await user.click(await within(dialog).findByRole("checkbox", { name: "Código ERP" }));
    await user.click(within(dialog).getByRole("button", { name: "Salvar" }));

    expect(await screen.findByText("Produto Suporte ERP atualizado.")).toHaveRole("status");
    expect(store.changes[0]?.body.collection_ids).toEqual([]);
    await waitFor(() => {
      expect(within(rowOf("Suporte ERP")).getByText("Nenhuma (sem fonte)")).toBeInTheDocument();
    });
  });

  it("test_products_page_validates_min_similarity", async () => {
    const user = userEvent.setup();
    const store = productStore();
    server.use(...store.handlers);
    await renderProducts();
    const dialog = await openEdit(user, "Suporte ERP");
    const minSimilarity = within(dialog).getByLabelText("Similaridade mínima");

    await user.clear(minSimilarity);
    await user.type(minSimilarity, "1,2");
    await user.click(within(dialog).getByRole("button", { name: "Salvar" }));

    expect(await within(dialog).findByText("Informe um número de 0 a 1.")).toBeInTheDocument();
    expect(store.changes).toEqual([]);
  });

  it("test_products_page_shows_collection_invalid_error", async () => {
    const user = userEvent.setup();
    await renderProducts();
    server.use(updateProductFails(422, "product_collection_invalid"));
    const dialog = await openEdit(user, "Suporte ERP");

    await user.click(within(dialog).getByRole("button", { name: "Salvar" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent(
      "Escolha apenas coleções deste workspace.",
    );
  });

  it("test_products_page_without_collections_points_to_collections", async () => {
    const user = userEvent.setup();
    server.use(...collectionsAs([]));
    await renderProducts();
    const dialog = await openCreate(user);

    expect(
      await within(dialog).findByText(/Nenhuma coleção cadastrada neste workspace./),
    ).toBeVisible();
    expect(within(dialog).getByRole("link", { name: "Ir para coleções" })).toHaveAttribute(
      "href",
      `/w/${WORKSPACE_ID}/collections`,
    );
    expect(within(dialog).getByText(NO_COLLECTION_WARNING)).toBeVisible();
  });

  it("test_products_page_retries_loading_collections", async () => {
    const user = userEvent.setup();
    server.use(collectionsServerError);
    await renderProducts();
    const dialog = await openCreate(user);

    expect(await within(dialog).findByText("Não foi possível carregar as coleções.")).toHaveRole(
      "alert",
    );
    server.use(...collectionsAs());
    await user.click(within(dialog).getByRole("button", { name: "Tentar novamente" }));

    expect(await within(dialog).findByRole("checkbox", { name: "Manuais" })).toBeVisible();
  });
});

describe("ProductsPage delete", () => {
  it("test_products_page_delete_warns_about_conversations", async () => {
    const user = userEvent.setup();
    const store = productStore();
    server.use(...store.handlers);
    await renderProducts();

    await user.click(screen.getByRole("button", { name: "Excluir Rascunho" }));
    const dialog = await screen.findByRole("alertdialog", {
      name: "Excluir o produto Rascunho?",
    });
    expect(dialog).toHaveAccessibleDescription(
      "As conversas deste produto e os níveis dos membros nele também serão excluídos, sem volta. Para manter o histórico, desative o produto em vez de excluí-lo.",
    );
    await user.click(within(dialog).getByRole("button", { name: "Excluir" }));

    expect(await screen.findByText("O produto Rascunho foi excluído.")).toHaveRole("status");
    expect(store.deleted).toEqual([OTHER_PRODUCT_ID]);
    await waitFor(() => {
      expect(screen.queryByRole("button", { name: "Excluir Rascunho" })).not.toBeInTheDocument();
    });
  });

  it("test_products_page_shows_delete_error", async () => {
    const user = userEvent.setup();
    await renderProducts();
    server.use(deleteProductFails(404, "not_found"));

    await user.click(screen.getByRole("button", { name: "Excluir Suporte ERP" }));
    await user.click(
      within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Excluir" }),
    );

    expect(await screen.findByRole("alert")).toHaveTextContent("O item procurado não existe.");
    expect(rowOf("Suporte ERP")).toBeInTheDocument();
  });
});
