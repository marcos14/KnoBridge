import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Role } from "@/lib/api/auth";
import { RUN_POLL_INTERVAL_MS } from "@/lib/api/sources";
import {
  makeMe,
  makeRun,
  makeRunError,
  makeRuns,
  makeSource,
  makeSourceDocument,
  makeWorkspace,
  OTHER_RUN_ID,
  RUN_ID,
  SOURCE_ID,
  WORKSPACE_ID,
} from "@/test/factories";
import {
  collectionsServerError,
  meAs,
  runServerError,
  sourceActionFails,
  sourceDocumentsServerError,
  sourceRunsServerError,
  sourceServerError,
  sourceStore,
} from "@/test/handlers";
import { renderWithProviders } from "@/test/renderWithProviders";
import { server } from "@/test/server";
import { makeTicketsSource, TICKETS_SOURCE_ID } from "@/test/ticketFactories";

const PATH = `/w/${WORKSPACE_ID}/sources/${SOURCE_ID}`;
const RUNS = "Execuções da fonte";
const ERRORS = "Erros por documento";
const DOCUMENTS = "Documentos da fonte";

function asRole(role: Role) {
  server.use(meAs(makeMe({ workspaces: [makeWorkspace({ role })] })));
}

async function renderDetail() {
  const result = renderWithProviders({ path: PATH });
  await screen.findByRole("heading", { level: 1, name: "erp-core" });
  return result;
}

function table(name: string) {
  return screen.findByRole("table", { name });
}

function rowsOf(element: HTMLElement): HTMLElement[] {
  // The first row holds the headers.
  return within(element).getAllByRole("row").slice(1);
}

afterEach(() => {
  vi.useRealTimers();
});

describe("SourceDetail header", () => {
  it("test_source_detail_shows_settings_and_back_link", async () => {
    server.use(
      ...sourceStore([
        makeSource({
          config: { path: "/sources/erp-core", branch: "main" },
          include_globs: ["src/**"],
          exclude_globs: ["tests/**", "docs/**"],
        }),
      ]).handlers,
    );
    await renderDetail();

    expect(screen.getByRole("link", { name: "Voltar para fontes" })).toHaveAttribute(
      "href",
      `/w/${WORKSPACE_ID}/sources`,
    );
    expect(screen.getByText("Repositório Git na coleção Código ERP")).toBeInTheDocument();
    expect(screen.getByText("Origem: /sources/erp-core")).toBeInTheDocument();
    expect(screen.getByText("Branch: main")).toBeInTheDocument();
    expect(screen.getByText("Incluir: src/**")).toBeInTheDocument();
    expect(screen.getByText("Excluir: tests/**, docs/**")).toBeInTheDocument();
    expect(screen.getByText("Documentos indexados: 42")).toBeInTheDocument();
  });

  it("test_source_detail_tests_the_connection", async () => {
    const user = userEvent.setup();
    const store = sourceStore();
    server.use(...store.handlers);
    await renderDetail();

    await user.click(screen.getByRole("button", { name: "Testar conexão" }));

    expect(await screen.findByText("A fonte erp-core está acessível.")).toHaveRole("status");
    expect(store.tested).toEqual([SOURCE_ID]);
  });

  it("test_source_detail_reports_failed_connection_test", async () => {
    const user = userEvent.setup();
    server.use(
      ...sourceStore([makeSource()], {
        testResults: {
          [SOURCE_ID]: {
            ok: false,
            error: { code: "path_outside_root", message: "Outside.", details: null },
          },
        },
      }).handlers,
    );
    await renderDetail();

    await user.click(screen.getByRole("button", { name: "Testar conexão" }));

    expect(
      await screen.findByText(
        "A fonte erp-core não respondeu: O caminho está fora da pasta liberada para fontes locais.",
      ),
    ).toHaveRole("alert");
  });

  it("test_source_detail_shows_test_request_failure", async () => {
    const user = userEvent.setup();
    server.use(sourceActionFails("test", 403, "forbidden"), ...sourceStore().handlers);
    await renderDetail();

    await user.click(screen.getByRole("button", { name: "Testar conexão" }));

    expect(await screen.findByText("Você não tem permissão para fazer isso.")).toHaveRole("alert");
  });

  it("test_source_detail_edits_and_syncs", async () => {
    const user = userEvent.setup();
    const store = sourceStore([makeSource({ config: { path: "/sources/erp-core" } })]);
    server.use(...store.handlers);
    await renderDetail();

    await user.click(screen.getByRole("button", { name: "Editar erp-core" }));
    const dialog = await screen.findByRole("dialog", { name: "Editar fonte" });
    await user.clear(within(dialog).getByLabelText("Nome"));
    await user.type(within(dialog).getByLabelText("Nome"), "erp");
    await user.click(within(dialog).getByRole("button", { name: "Salvar" }));
    expect(await screen.findByText("Fonte erp atualizada.")).toHaveRole("status");

    await user.click(await screen.findByRole("button", { name: "Sincronizar erp agora" }));
    expect(await screen.findByText("Sincronização de erp na fila.")).toHaveRole("status");
    expect(store.synced).toEqual([SOURCE_ID]);
  });

  it("test_source_detail_viewer_reads_without_actions", async () => {
    asRole("viewer");
    server.use(...sourceStore().handlers);
    await renderDetail();

    expect(await table(RUNS)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Testar conexão" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Sincronizar/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Editar erp-core" })).not.toBeInTheDocument();
    expect(await table(DOCUMENTS)).toBeInTheDocument();
  });

  it("test_source_detail_of_unknown_source_says_not_found", async () => {
    server.use(...sourceStore([]).handlers);
    renderWithProviders({ path: PATH });

    expect(
      await screen.findByRole("heading", { level: 1, name: "Fonte não encontrada." }),
    ).toBeInTheDocument();
  });

  it("test_source_detail_retries_after_load_failure", async () => {
    const user = userEvent.setup();
    server.use(sourceServerError, collectionsServerError);
    renderWithProviders({ path: PATH });

    expect(await screen.findByText("Não foi possível carregar a fonte.")).toHaveRole("alert");
    server.resetHandlers();
    await user.click(screen.getByRole("button", { name: "Tentar novamente" }));

    expect(await screen.findByRole("heading", { level: 1, name: "erp-core" })).toBeInTheDocument();
  });
});

describe("SourceDetail reindex", () => {
  it("test_source_detail_reindexes_after_confirmation", async () => {
    const user = userEvent.setup();
    const store = sourceStore();
    server.use(...store.handlers);
    await renderDetail();

    await user.click(screen.getByRole("button", { name: "Reindexar" }));
    const dialog = await screen.findByRole("alertdialog", { name: "Reindexar erp-core?" });
    expect(dialog).toHaveTextContent("Todos os documentos da fonte são processados de novo");
    await user.click(within(dialog).getByRole("button", { name: "Reindexar" }));

    expect(await screen.findByText("Reindexação de erp-core na fila.")).toHaveRole("status");
    expect(store.reindexed).toEqual([SOURCE_ID]);
    // The queued run disables it until the run ends.
    expect(await screen.findByRole("button", { name: "Reindexar" })).toBeDisabled();
  });

  it("test_source_detail_reindex_dismissed_does_nothing", async () => {
    const user = userEvent.setup();
    const store = sourceStore();
    server.use(...store.handlers);
    await renderDetail();

    await user.click(screen.getByRole("button", { name: "Reindexar" }));
    await user.click(
      within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Cancelar" }),
    );

    await waitFor(() => {
      expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    });
    expect(store.reindexed).toEqual([]);
  });

  it("test_source_detail_reindex_failure_shows_reason", async () => {
    const user = userEvent.setup();
    server.use(sourceActionFails("reindex", 503, "sync_unavailable"));
    await renderDetail();

    await user.click(screen.getByRole("button", { name: "Reindexar" }));
    await user.click(
      within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Reindexar" }),
    );

    expect(
      await screen.findByText(
        "O serviço de sincronização está indisponível. Tente de novo em instantes.",
      ),
    ).toHaveRole("alert");
  });

  it("test_source_detail_reindex_disabled_for_inactive_source", async () => {
    server.use(...sourceStore([makeSource({ active: false })]).handlers);
    await renderDetail();

    expect(screen.getByRole("button", { name: "Reindexar" })).toBeDisabled();
  });

  it("test_source_detail_tickets_source_explains_why_it_cannot_reindex", async () => {
    server.use(...sourceStore([makeTicketsSource()]).handlers);
    renderWithProviders({ path: `/w/${WORKSPACE_ID}/sources/${TICKETS_SOURCE_ID}` });

    const button = await screen.findByRole("button", { name: "Reindexar" });
    expect(button).toBeDisabled();
    expect(button).toHaveAccessibleDescription(
      "Fontes de chamados não são reindexadas: os chamados brutos são apagados depois de indexados.",
    );
  });

  it("test_source_detail_viewer_has_no_reindex", async () => {
    asRole("viewer");
    server.use(...sourceStore().handlers);
    await renderDetail();

    expect(screen.queryByRole("button", { name: "Reindexar" })).not.toBeInTheDocument();
  });
});

describe("SourceDetail runs", () => {
  it("test_source_detail_lists_runs_with_counts_cost_and_duration", async () => {
    server.use(...sourceStore().handlers);
    await renderDetail();

    const [scheduled, first] = rowsOf(await table(RUNS));
    expect(scheduled).toHaveTextContent("Concluída");
    expect(scheduled).toHaveTextContent("Agendada");
    expect(scheduled).toHaveTextContent("1 / 3 / 1 / 2");
    expect(scheduled).toHaveTextContent("2.400");
    expect(scheduled).toHaveTextContent(/US\$\s0,000048/);
    expect(scheduled).toHaveTextContent("45 s");
    expect(scheduled).toHaveTextContent("Selecionada");
    expect(first).toHaveTextContent("Manual");
    expect(first).toHaveTextContent("42 / 0 / 0 / 0");
    expect(first).toHaveTextContent("51.000");
    expect(first).toHaveTextContent(/US\$\s0,0010/);
  });

  it("test_source_detail_shows_errors_of_the_selected_run", async () => {
    const user = userEvent.setup();
    server.use(
      ...sourceStore([makeSource()], {
        runs: {
          [SOURCE_ID]: [
            ...makeRuns(),
            makeRun({
              id: "00000000-0000-4000-8000-0000000001c3",
              status: "failed",
              error: "Repository not found.",
              created_at: "2026-10-01T09:00:00Z",
              started_at: null,
              finished_at: "2026-10-01T09:00:00Z",
            }),
          ],
        },
        errors: {
          [OTHER_RUN_ID]: [
            makeRunError(),
            makeRunError({
              id: "00000000-0000-4000-8000-0000000001f2",
              document_key: "src/big.bin",
              stage: "embed",
              code: "embedding_failed",
              message: "Too large.",
            }),
          ],
        },
      }).handlers,
    );
    await renderDetail();

    const errors = await table(ERRORS);
    const [parse, embed] = rowsOf(errors);
    expect(parse).toHaveTextContent("src/nota.py");
    expect(parse).toHaveTextContent("Análise");
    expect(parse).toHaveTextContent("parse_failed");
    expect(parse).toHaveTextContent("Unexpected indentation at line 12.");
    expect(embed).toHaveTextContent("Embedding");

    const runs = await table(RUNS);
    const showErrors = within(runs).getAllByRole("button", { name: /^Ver erros da execução de/ });
    expect(showErrors).toHaveLength(2);
    expect(rowsOf(runs)[2]).toHaveTextContent("Falhou");
    expect(rowsOf(runs)[2]).toHaveTextContent("—");
    const [first, failed] = showErrors as [HTMLElement, HTMLElement];
    await user.click(first);
    expect(await screen.findByText("Nenhum documento falhou nesta execução.")).toBeInTheDocument();

    await user.click(failed);
    expect(await screen.findByText("Falha da execução: Repository not found.")).toBeInTheDocument();
  });

  it("test_source_detail_pages_run_errors", async () => {
    const user = userEvent.setup();
    const many = Array.from({ length: 25 }, (_, index) =>
      makeRunError({
        id: `00000000-0000-4000-8000-${String(800 + index).padStart(12, "0")}`,
        document_key: `src/f${String(index).padStart(2, "0")}.py`,
      }),
    );
    server.use(...sourceStore([makeSource()], { errors: { [OTHER_RUN_ID]: many } }).handlers);
    await renderDetail();

    const errors = await table(ERRORS);
    expect(rowsOf(errors)).toHaveLength(20);
    const pager = screen.getByRole("navigation", { name: new RegExp(ERRORS) });
    await user.click(within(pager).getByRole("button", { name: "Próxima" }));

    expect(await within(pager).findByText("21–25 de 25")).toBeInTheDocument();
    expect(await within(errors).findByText("src/f24.py")).toBeInTheDocument();
  });

  it("test_source_detail_pages_runs", async () => {
    const user = userEvent.setup();
    const runs = Array.from({ length: 12 }, (_, index) =>
      makeRun({
        id: `00000000-0000-4000-8000-${String(600 + index).padStart(12, "0")}`,
        documents_new: index,
      }),
    );
    server.use(...sourceStore([makeSource()], { runs: { [SOURCE_ID]: runs } }).handlers);
    await renderDetail();

    const pager = await screen.findByRole("navigation", { name: new RegExp(RUNS) });
    await user.click(within(pager).getByRole("button", { name: "Próxima" }));

    expect(await within(pager).findByText("11–12 de 12")).toBeInTheDocument();
  });

  it("test_source_detail_without_runs_says_so", async () => {
    server.use(
      ...sourceStore([makeSource({ last_run: null })], { runs: { [SOURCE_ID]: [] } }).handlers,
    );
    await renderDetail();

    expect(await screen.findByText("Nenhuma execução ainda.")).toBeInTheDocument();
    expect(screen.queryByRole("table", { name: ERRORS })).not.toBeInTheDocument();
  });

  it("test_source_detail_retries_runs_and_errors_after_failure", async () => {
    const user = userEvent.setup();
    server.use(sourceRunsServerError, ...sourceStore().handlers);
    await renderDetail();

    expect(await screen.findByText("Não foi possível carregar as execuções.")).toHaveRole("alert");
    server.use(runServerError, ...sourceStore().handlers);
    await user.click(screen.getByRole("button", { name: "Tentar novamente" }));

    expect(await screen.findByText("Não foi possível carregar os erros da execução.")).toHaveRole(
      "alert",
    );
    server.use(...sourceStore().handlers);
    await user.click(screen.getByRole("button", { name: "Tentar novamente" }));
    expect(await table(ERRORS)).toBeInTheDocument();
  });

  it("test_source_detail_polls_while_the_run_is_active_and_stops_after", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const running = makeRun({
      id: RUN_ID,
      status: "running",
      started_at: "2026-10-10T11:59:00Z",
      finished_at: null,
    });
    const store = sourceStore([makeSource({ last_run: running })], {
      runs: { [SOURCE_ID]: [running] },
    });
    server.use(...store.handlers);
    await renderDetail();
    const [row] = rowsOf(await table(RUNS));
    expect(row).toHaveTextContent("Em execução");
    expect(row).toHaveTextContent("1 min");

    store.finishRun(SOURCE_ID, "succeeded");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(RUN_POLL_INTERVAL_MS);
    });
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Sincronizar erp-core agora" })).toBeEnabled();
    });
    expect(rowsOf(screen.getByRole("table", { name: RUNS }))[0]).toHaveTextContent("Concluída");

    const reads = store.reads.length;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(RUN_POLL_INTERVAL_MS * 3);
    });
    expect(store.reads).toHaveLength(reads);
  });
});

describe("SourceDetail documents", () => {
  it("test_source_detail_lists_and_filters_documents", async () => {
    const user = userEvent.setup();
    const store = sourceStore();
    server.use(...store.handlers);
    await renderDetail();

    const documents = await table(DOCUMENTS);
    expect(rowsOf(documents)).toHaveLength(3);
    expect(within(documents).getByText("Fechamento do caixa")).toBeInTheDocument();
    expect(within(documents).getByText("docs/fechamento.md")).toBeInTheDocument();
    expect(within(documents).getByText("python")).toBeInTheDocument();

    await user.type(screen.getByLabelText("Buscar por caminho"), " caixa ");
    await user.click(screen.getByRole("button", { name: "Buscar" }));
    await waitFor(() => {
      expect(rowsOf(screen.getByRole("table", { name: DOCUMENTS }))).toHaveLength(1);
    });
    expect(store.documentQueries.at(-1)?.get("path")).toBe("caixa");
    expect(store.documentQueries.at(-1)?.get("path_match")).toBe("contains");

    await user.clear(screen.getByLabelText("Buscar por caminho"));
    await user.click(screen.getByRole("button", { name: "Buscar" }));
    await user.click(screen.getByRole("combobox", { name: "Tipo de documento" }));
    await user.click(await screen.findByRole("option", { name: "Commits" }));
    await waitFor(() => {
      expect(rowsOf(screen.getByRole("table", { name: DOCUMENTS }))).toHaveLength(1);
    });
    expect(store.documentQueries.at(-1)?.get("kind")).toBe("commit");
    expect(store.documentQueries.at(-1)?.has("path")).toBe(false);
    expect(screen.getByText("Corrige o fechamento do caixa")).toBeInTheDocument();

    await user.click(screen.getByRole("combobox", { name: "Tipo de documento" }));
    await user.click(await screen.findByRole("option", { name: "Todos" }));
    await waitFor(() => {
      expect(rowsOf(screen.getByRole("table", { name: DOCUMENTS }))).toHaveLength(3);
    });
  });

  it("test_source_detail_shows_documents_not_yet_indexed_and_empty_search", async () => {
    const user = userEvent.setup();
    server.use(
      ...sourceStore([makeSource()], {
        documents: { [SOURCE_ID]: [makeSourceDocument({ indexed_at: null })] },
      }).handlers,
    );
    await renderDetail();

    expect(await screen.findByText("Ainda não indexado")).toBeInTheDocument();
    await user.type(screen.getByLabelText("Buscar por caminho"), "nada");
    await user.click(screen.getByRole("button", { name: "Buscar" }));

    expect(await screen.findByText("Nenhum documento encontrado.")).toBeInTheDocument();
  });

  it("test_source_detail_retries_documents_after_failure", async () => {
    const user = userEvent.setup();
    server.use(sourceDocumentsServerError, ...sourceStore().handlers);
    await renderDetail();

    expect(await screen.findByText("Não foi possível carregar os documentos.")).toHaveRole("alert");
    server.use(...sourceStore().handlers);
    await user.click(screen.getByRole("button", { name: "Tentar novamente" }));

    expect(await table(DOCUMENTS)).toBeInTheDocument();
  });
});
