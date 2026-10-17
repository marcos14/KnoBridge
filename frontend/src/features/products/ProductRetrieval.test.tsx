import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { Role } from "@/lib/api/auth";
import type { Product } from "@/lib/api/products";
import { makeMe, makeProduct, makeProducts, makeWorkspace, WORKSPACE_ID } from "@/test/factories";
import { meAs, productStore } from "@/test/handlers";
import { renderWithProviders } from "@/test/renderWithProviders";
import { server } from "@/test/server";

const PATH = `/w/${WORKSPACE_ID}/products`;
const UNAVAILABLE =
  "Esta instância não tem reranker: ele é opcional e vem desligado. Para ligar, veja a seção Reranker do guia Subir o ambiente (docs/guias/subir-ambiente.md). A opção fica gravada como está e passa a valer quando houver um.";

type User = ReturnType<typeof userEvent.setup>;

function withReranker(products: Product[]): Product[] {
  return products.map((product) => ({ ...product, rerank_available: true }));
}

async function renderProducts(products: Product[], role: Role = "owner") {
  server.use(meAs(makeMe({ workspaces: [makeWorkspace({ role })] })));
  const store = productStore(products);
  server.use(...store.handlers);
  const user = userEvent.setup();
  renderWithProviders({ path: PATH });
  await screen.findByRole("table", { name: "Produtos do workspace" });
  return { user, store };
}

async function openEdit(user: User, name = "Suporte ERP") {
  await user.click(screen.getByRole("button", { name: `Editar ${name}` }));
  return screen.findByRole("dialog", { name: "Editar produto" });
}

describe("Product retrieval options", () => {
  it.each<Role>(["owner", "admin", "editor"])(
    "test_product_rerank_can_be_turned_on_by_%s",
    async (role) => {
      const { user, store } = await renderProducts(withReranker(makeProducts()), role);
      const dialog = await openEdit(user);
      const rerank = within(dialog).getByRole("checkbox", { name: "Reordenar trechos" });

      expect(rerank).not.toBeChecked();
      expect(rerank).toBeEnabled();
      expect(rerank).toHaveAccessibleDescription(/^O reranker da instância reordena/);
      await user.click(rerank);
      await user.click(within(dialog).getByRole("button", { name: "Salvar" }));

      expect(await screen.findByText("Produto Suporte ERP atualizado.")).toHaveRole("status");
      expect(store.changes[0]?.body.rerank).toBe(true);
    },
  );

  it("test_product_rerank_can_be_turned_off", async () => {
    const products = withReranker([makeProduct({ rerank: true })]);
    const { user, store } = await renderProducts(products);
    const dialog = await openEdit(user);
    const rerank = within(dialog).getByRole("checkbox", { name: "Reordenar trechos" });

    expect(rerank).toBeChecked();
    await user.click(rerank);
    await user.click(within(dialog).getByRole("button", { name: "Salvar" }));

    await screen.findByText("Produto Suporte ERP atualizado.");
    expect(store.changes[0]?.body.rerank).toBe(false);
  });

  it("test_product_rerank_is_disabled_without_a_reranker", async () => {
    const { user } = await renderProducts(makeProducts());
    const dialog = await openEdit(user);

    const rerank = within(dialog).getByRole("checkbox", { name: "Reordenar trechos" });
    expect(rerank).toBeDisabled();
    expect(rerank).not.toBeChecked();
    expect(rerank).toHaveAccessibleDescription(UNAVAILABLE);
  });

  it("test_product_create_starts_without_reranking_and_can_turn_it_on", async () => {
    const { user, store } = await renderProducts(withReranker(makeProducts()));
    await user.click(screen.getByRole("button", { name: "Novo produto" }));
    const dialog = await screen.findByRole("dialog", { name: "Novo produto" });

    const rerank = within(dialog).getByRole("checkbox", { name: "Reordenar trechos" });
    expect(rerank).toBeEnabled();
    expect(rerank).not.toBeChecked();
    await user.click(rerank);
    await user.type(within(dialog).getByLabelText("Nome"), "Financeiro");
    await user.click(within(dialog).getByRole("button", { name: "Salvar" }));

    await screen.findByText("Produto Financeiro criado.");
    expect(store.created[0]).toMatchObject({ rerank: true, min_similarity: null });
  });

  it("test_product_create_without_products_offers_the_rerank_option", async () => {
    const { user } = await renderProducts([]);
    await user.click(screen.getByRole("button", { name: "Novo produto" }));
    const dialog = await screen.findByRole("dialog", { name: "Novo produto" });

    expect(within(dialog).getByRole("checkbox", { name: "Reordenar trechos" })).toBeEnabled();
  });

  it("test_product_shows_the_floor_in_use_and_goes_back_to_the_model_default", async () => {
    const { user, store } = await renderProducts(makeProducts());
    const dialog = await openEdit(user);

    const floors = within(dialog).getByRole("list", {
      name: "Limiar em uso, pelo que está salvo:",
    });
    expect(floors).toHaveTextContent("text-embedding-3-small: 0,35 (deste produto)");
    await user.clear(within(dialog).getByLabelText("Similaridade mínima"));
    await user.click(within(dialog).getByRole("button", { name: "Salvar" }));

    await screen.findByText("Produto Suporte ERP atualizado.");
    expect(store.changes[0]?.body.min_similarity).toBeNull();
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
    const reopened = await openEdit(user);
    expect(within(reopened).getByLabelText("Similaridade mínima")).toHaveValue("");
    expect(
      within(reopened).getByRole("list", { name: "Limiar em uso, pelo que está salvo:" }),
    ).toHaveTextContent("text-embedding-3-small: 0,35 (padrão do modelo)");
  });

  it("test_product_without_collections_shows_no_floor_in_use", async () => {
    const { user } = await renderProducts([
      makeProduct({ collection_ids: [], effective_min_similarity: [] }),
    ]);
    const dialog = await openEdit(user);

    expect(within(dialog).queryByText("Limiar em uso, pelo que está salvo:")).toBeNull();
  });

  it("test_product_floor_of_a_model_outside_the_table_says_so", async () => {
    const { user } = await renderProducts([
      makeProduct({
        min_similarity: null,
        effective_min_similarity: [
          { embedding_model: "modelo-local", value: 0.35, source: "fallback" },
          { embedding_model: "openai/gemini-embedding-001", value: 0.6, source: "model" },
        ],
      }),
    ]);
    const dialog = await openEdit(user);

    const floors = within(dialog).getByRole("list", {
      name: "Limiar em uso, pelo que está salvo:",
    });
    expect(
      within(floors)
        .getAllByRole("listitem")
        .map((item) => item.textContent),
    ).toEqual([
      "modelo-local: 0,35 (padrão geral, modelo sem padrão próprio)",
      "openai/gemini-embedding-001: 0,60 (padrão do modelo)",
    ]);
  });
});
