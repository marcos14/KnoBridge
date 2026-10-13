import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { Role } from "@/lib/api/auth";
import {
  COLLECTION_ID,
  makeMe,
  makeSource,
  makeWorkspace,
  OTHER_COLLECTION_ID,
  RUN_ID,
  SOURCE_ID,
  WORKSPACE_ID,
} from "@/test/factories";
import {
  collectionSyncAs,
  collectionSyncFails,
  collectionServerError,
  collectionStore,
  collectionsAs,
  meAs,
  pendingPost,
  providersServerError,
  searchFails,
  searchRecorder,
  sourcesAs,
  sourcesServerError,
} from "@/test/handlers";
import { renderWithProviders } from "@/test/renderWithProviders";
import { server } from "@/test/server";

const PATH = `/w/${WORKSPACE_ID}/collections/${COLLECTION_ID}`;

type User = ReturnType<typeof userEvent.setup>;

function asRole(role: Role) {
  server.use(meAs(makeMe({ workspaces: [makeWorkspace({ role })] })));
}

async function renderDetail(path = PATH) {
  const result = renderWithProviders({ path });
  await screen.findByRole("heading", { level: 1, name: /Código ERP|Manuais/ });
  return result;
}

async function search(user: User, query: string, minSimilarity?: string) {
  await user.type(screen.getByLabelText("Pergunta ou termos"), query);
  if (minSimilarity !== undefined) {
    await user.type(screen.getByLabelText("Similaridade mínima (opcional)"), minSimilarity);
  }
  await user.click(screen.getByRole("button", { name: "Buscar" }));
}

describe("CollectionDetail", () => {
  it("test_collection_detail_shows_counts_and_sources", async () => {
    await renderDetail();

    expect(screen.getByText("Modelo de embedding: text-embedding-3-small")).toBeInTheDocument();
    expect(screen.getByText("Fontes: 1 · Documentos: 42 · Trechos: 310")).toBeInTheDocument();
    const sources = await screen.findByRole("table", { name: "Fontes da coleção" });
    const row = within(sources)
      .getAllByRole("row")
      .find((item) => item.textContent.includes("erp-core"));
    expect(row).toHaveTextContent("Repositório Git");
    expect(row).toHaveTextContent("Concluída");
    expect(screen.getByRole("link", { name: "Ir para fontes" })).toHaveAttribute(
      "href",
      `/w/${WORKSPACE_ID}/sources`,
    );
    expect(screen.getByRole("link", { name: "Voltar para coleções" })).toHaveAttribute(
      "href",
      `/w/${WORKSPACE_ID}/collections`,
    );
  });

  it("test_collection_detail_lists_only_its_sources_with_status", async () => {
    const synced = makeSource().last_run;
    server.use(
      sourcesAs([
        makeSource({ collection_id: OTHER_COLLECTION_ID, name: "manual-pdf" }),
        makeSource({
          id: "00000000-0000-4000-8000-0000000001b9",
          collection_id: OTHER_COLLECTION_ID,
          name: "pasta-docs",
          kind: "folder",
          last_run: null,
        }),
        makeSource({ name: "erp-core" }),
        makeSource({
          id: "00000000-0000-4000-8000-0000000001b8",
          collection_id: OTHER_COLLECTION_ID,
          name: "wiki",
          last_run: synced === null ? null : { ...synced, status: "failed" },
        }),
      ]),
    );
    await renderDetail(`/w/${WORKSPACE_ID}/collections/${OTHER_COLLECTION_ID}`);

    const sources = await screen.findByRole("table", { name: "Fontes da coleção" });
    expect(within(sources).queryByText("erp-core")).not.toBeInTheDocument();
    expect(within(sources).getByText("Pasta")).toBeInTheDocument();
    expect(within(sources).getByText("Nunca sincronizada")).toBeInTheDocument();
    expect(within(sources).getByText("Falhou")).toBeInTheDocument();
  });

  it("test_collection_detail_without_sources_says_so", async () => {
    server.use(sourcesAs([]));
    await renderDetail();

    expect(await screen.findByText("Nenhuma fonte nesta coleção.")).toBeInTheDocument();
  });

  it("test_collection_detail_retries_sources", async () => {
    const user = userEvent.setup();
    server.use(sourcesServerError);
    await renderDetail();

    expect(await screen.findByText("Não foi possível carregar as fontes.")).toHaveRole("alert");
    server.use(sourcesAs());
    await user.click(screen.getByRole("button", { name: "Tentar novamente" }));

    expect(await screen.findByRole("table", { name: "Fontes da coleção" })).toBeInTheDocument();
  });

  it("test_collection_detail_not_found", async () => {
    renderWithProviders({
      path: `/w/${WORKSPACE_ID}/collections/00000000-0000-4000-8000-000000000999`,
    });

    expect(
      await screen.findByRole("heading", { level: 1, name: "Coleção não encontrada." }),
    ).toBeInTheDocument();
  });

  it("test_collection_detail_retries_after_load_failure", async () => {
    const user = userEvent.setup();
    server.use(collectionServerError);
    renderWithProviders({ path: PATH });

    expect(await screen.findByText("Não foi possível carregar a coleção.")).toHaveRole("alert");
    server.use(...collectionsAs());
    await user.click(screen.getByRole("button", { name: "Tentar novamente" }));

    expect(
      await screen.findByRole("heading", { level: 1, name: "Código ERP" }),
    ).toBeInTheDocument();
  });

  it("test_collection_detail_edits_and_refreshes", async () => {
    const user = userEvent.setup();
    server.use(...collectionStore().handlers);
    await renderDetail();

    const edit = screen.getByRole("button", { name: "Editar Código ERP" });
    await waitFor(() => {
      expect(edit).toBeEnabled();
    });
    await user.click(edit);
    const dialog = await screen.findByRole("dialog", { name: "Editar coleção" });
    await user.clear(within(dialog).getByLabelText("Descrição"));
    await user.click(within(dialog).getByRole("button", { name: "Salvar" }));

    expect(await screen.findByText("Coleção Código ERP atualizada.")).toHaveRole("status");
    expect(screen.queryByText("Repositório do ERP e seus commits.")).not.toBeInTheDocument();
  });

  it("test_collection_detail_viewer_can_search_but_not_edit", async () => {
    const user = userEvent.setup();
    asRole("viewer");
    server.use(providersServerError);
    const recorder = searchRecorder();
    server.use(recorder.handler);
    await renderDetail();

    expect(screen.queryByRole("button", { name: /Editar/ })).not.toBeInTheDocument();
    await search(user, "fechar caixa");

    expect(await screen.findByText("Trechos encontrados: 2")).toBeInTheDocument();
  });
});

describe("CollectionDetail sync all", () => {
  const PAUSED_ID = "00000000-0000-4000-8000-0000000000c9";
  const RUNNING_ID = "00000000-0000-4000-8000-0000000000ca";
  const SOURCES = [
    makeSource(),
    makeSource({ id: PAUSED_ID, name: "docs-antigas", active: false }),
    makeSource({ id: RUNNING_ID, name: "portal" }),
  ];

  it("test_collection_detail_syncs_all_and_lists_skipped_with_reason", async () => {
    const user = userEvent.setup();
    const sync = collectionSyncAs({
      started: [{ source_id: SOURCE_ID, run_id: RUN_ID }],
      skipped: [
        { source_id: PAUSED_ID, reason: "source_inactive" },
        { source_id: RUNNING_ID, reason: "sync_already_running" },
      ],
    });
    server.use(sourcesAs(SOURCES), sync.handler);
    await renderDetail();

    await user.click(await screen.findByRole("button", { name: "Sincronizar todas" }));

    expect(await screen.findByText("Sincronização iniciada em 1 fonte.")).toBeInTheDocument();
    expect(screen.getByText("2 fontes ficaram de fora:")).toBeInTheDocument();
    expect(screen.getByText("docs-antigas: está desativada")).toBeInTheDocument();
    expect(screen.getByText("portal: já está sincronizando")).toBeInTheDocument();
    expect(sync.synced).toEqual([COLLECTION_ID]);
  });

  it("test_collection_detail_sync_all_without_start_says_so", async () => {
    const user = userEvent.setup();
    const unknown = "00000000-0000-4000-8000-0000000000cb";
    server.use(
      sourcesAs([makeSource()]),
      collectionSyncAs({
        started: [],
        skipped: [
          { source_id: SOURCE_ID, reason: "sync_unavailable" },
          { source_id: unknown, reason: "source_inactive" },
        ],
      }).handler,
    );
    await renderDetail();

    await user.click(await screen.findByRole("button", { name: "Sincronizar todas" }));

    expect(await screen.findByText("Nenhuma sincronização foi iniciada.")).toBeInTheDocument();
    expect(
      screen.getByText("erp-core: o serviço de sincronização ficou indisponível"),
    ).toBeInTheDocument();
    expect(screen.getByText(`${unknown}: está desativada`)).toBeInTheDocument();
  });

  it("test_collection_detail_sync_all_failure_shows_reason", async () => {
    const user = userEvent.setup();
    server.use(collectionSyncFails(503, "sync_unavailable"));
    await renderDetail();

    await user.click(await screen.findByRole("button", { name: "Sincronizar todas" }));

    expect(
      await screen.findByText(
        "O serviço de sincronização está indisponível. Tente de novo em instantes.",
      ),
    ).toHaveRole("alert");
  });

  it("test_collection_detail_sync_all_disabled_without_sources", async () => {
    server.use(sourcesAs([]));
    await renderDetail();

    expect(await screen.findByRole("button", { name: "Sincronizar todas" })).toBeDisabled();
  });

  it("test_collection_detail_viewer_cannot_sync_all", async () => {
    asRole("viewer");
    await renderDetail();
    await screen.findByRole("table", { name: "Fontes da coleção" });

    expect(screen.queryByRole("button", { name: "Sincronizar todas" })).not.toBeInTheDocument();
  });
});

describe("CollectionDetail search", () => {
  it("test_search_shows_results_with_location_scores_and_snippet", async () => {
    const user = userEvent.setup();
    const recorder = searchRecorder();
    server.use(recorder.handler);
    await renderDetail();

    await search(user, "como fechar o caixa");

    const results = await screen.findByRole("list", { name: "Resultados da busca" });
    const items = within(results).getAllByRole("listitem");
    expect(items).toHaveLength(2);
    const [code, commit] = items as [HTMLElement, HTMLElement];
    expect(code).toHaveTextContent("src/caixa.py:10–24");
    expect(code).toHaveTextContent("Fusão 0,0328 · Vetorial 0,52 · Texto 0,120");
    expect(code).toHaveTextContent("Símbolo: fechar_caixa");
    expect(code).toHaveTextContent("Linguagem: python");
    const snippet = within(code).getByText(/def fechar_caixa/);
    expect(snippet.tagName).toBe("CODE");
    expect(snippet).toHaveClass("language-python");
    expect(commit).toHaveTextContent("commit abcdef1");
    expect(commit).toHaveTextContent("Fusão 0,0161 · Vetorial — · Texto 0,250");
    expect(recorder.bodies).toEqual([
      { query: "como fechar o caixa", limit: 10, min_similarity: 0.35 },
    ]);
  });

  it("test_search_empty_explains_threshold", async () => {
    const user = userEvent.setup();
    const recorder = searchRecorder([]);
    server.use(recorder.handler);
    await renderDetail();

    await search(user, "previsão do tempo", "0,8");

    expect(
      await screen.findByText(/Nenhum trecho passou do limiar de similaridade \(0,80\)/),
    ).toHaveRole("status");
    expect(recorder.bodies).toEqual([
      { query: "previsão do tempo", limit: 10, min_similarity: 0.8 },
    ]);
  });

  it("test_search_hint_shows_default_threshold", async () => {
    await renderDetail();

    expect(screen.getByLabelText("Similaridade mínima (opcional)")).toHaveAccessibleDescription(
      "De 0 a 1; em branco, 0,35. Trechos abaixo dela entram só se casarem com todos os termos da busca.",
    );
  });

  it("test_search_validates_query_and_threshold", async () => {
    const user = userEvent.setup();
    const recorder = searchRecorder();
    server.use(recorder.handler);
    await renderDetail();

    await user.type(screen.getByLabelText("Similaridade mínima (opcional)"), "1,5");
    await user.click(screen.getByRole("button", { name: "Buscar" }));

    expect(await screen.findByText("Digite o que deseja buscar.")).toBeInTheDocument();
    expect(screen.getByText("Informe um número de 0 a 1.")).toBeInTheDocument();
    expect(recorder.bodies).toEqual([]);
  });

  it("test_search_disables_button_while_searching", async () => {
    const user = userEvent.setup();
    server.use(pendingPost("*/v1/workspaces/:workspaceId/collections/:collectionId/search"));
    await renderDetail();

    await search(user, "caixa");

    expect(await screen.findByRole("button", { name: "Buscando…" })).toBeDisabled();
  });

  it("test_search_shows_provider_error", async () => {
    const user = userEvent.setup();
    server.use(searchFails(503, "provider_unavailable"));
    await renderDetail();

    await search(user, "caixa");

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "O provedor de LLM está indisponível no momento.",
    );
  });
});
