import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { stubDownloads } from "@/test/downloads";
import {
  harnessJobServerError,
  harnessJobsServerError,
  harnessModulesServerError,
  harnessStore,
  knowledgeExportFails,
  knowledgeServerError,
} from "@/test/handlers";
import { JOB_ID, makeHarnessJob, makeHarnessModules } from "@/test/harnessFactories";
import {
  APPROVED_TITLE,
  chooseFilter,
  KNOWLEDGE_TAB_PATH,
  knowledgeCard,
  renderKnowledgeTab,
  RULE_TITLE,
  useKnowledgeStores,
} from "@/test/knowledgeTab";
import { renderWithProviders } from "@/test/renderWithProviders";
import { server } from "@/test/server";

const ITEMS = "Itens de conhecimento";

// Review and edit live in KnowledgeReview.test.tsx.
describe("KnowledgeTab list", () => {
  it("test_knowledge_tab_shows_a_rule_with_resolution_and_evidence", async () => {
    useKnowledgeStores();
    await renderKnowledgeTab();

    const rule = await knowledgeCard(RULE_TITLE);
    expect(screen.getByRole("tab", { name: "Conhecimento" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(screen.getByRole("combobox", { name: "Módulo" })).toHaveTextContent("src/faturamento");
    expect(screen.getByText("4 itens")).toBeVisible();
    expect(within(rule).getByText("src-faturamento.R001")).toBeVisible();
    expect(within(rule).getByText("Pendente")).toBeVisible();
    expect(within(rule).getByText("Inferido")).toBeVisible();
    expect(
      within(rule).getByText("A nota só é emitida se o cliente tiver CNPJ válido."),
    ).toBeVisible();
    expect(
      within(rule).getByText("Completar o CNPJ no cadastro do cliente e emitir de novo."),
    ).toBeVisible();
    expect(within(rule).getByText("Como o usuário resolve")).toBeVisible();
    expect(within(rule).getByText("NOTAS_SERIE_PADRAO")).toBeVisible();
    expect(within(rule).getByText("intencional")).toBeVisible();
    const evidence = within(rule).getByRole("list", { name: `Evidências de ${RULE_TITLE}` });
    expect(within(evidence).getByText("src/faturamento/notas.ts:L80–L92")).toBeVisible();
    expect(within(evidence).getByText("emitirNota")).toBeVisible();
    expect(within(evidence).getByText(/throw new Error/, { selector: "code" })).toBeVisible();
    expect(within(rule).getByText(/Gerado por harness:codex no commit bbbbbbb/)).toBeVisible();
  });

  it("test_knowledge_tab_marks_changed_evidence_and_omitted_excerpts", async () => {
    useKnowledgeStores();
    await renderKnowledgeTab();

    const approved = await knowledgeCard(APPROVED_TITLE);
    expect(within(approved).getByText("Evidência mudou")).toBeVisible();
    expect(within(approved).getByText("Revisado")).toBeVisible();
    expect(within(approved).getByText("excerto omitido: arquivo sensível")).toBeVisible();
    expect(
      within(approved).getByText("excerto cortado; segredos ocultados no excerto"),
    ).toBeVisible();
    expect(within(approved).queryByText("Mensagem exibida")).not.toBeInTheDocument();
    const discarded = await knowledgeCard("Série padrão da nota fiscal");
    expect(within(discarded).getByText("Descartado")).toBeVisible();
    expect(within(discarded).getByText("Editado")).toBeVisible();
  });

  it("test_knowledge_tab_shows_the_module_enrichment_with_markers", async () => {
    useKnowledgeStores();
    await renderKnowledgeTab();

    const enrichment = await knowledgeCard("src/faturamento");
    expect(within(enrichment).getByText("Módulo", { selector: "span" })).toBeVisible();
    expect(
      within(enrichment).getByText("Emite e cancela notas fiscais a partir dos pedidos."),
    ).toBeVisible();
    expect(within(enrichment).getByText("Abrir o pedido faturado.")).toBeVisible();
    expect(within(enrichment).getAllByText("[2]")).toHaveLength(2);
    expect(within(enrichment).getByText("Por que a nota não sai?")).toBeVisible();
    expect(within(enrichment).getByText("(Há um ramo sem tratamento.)")).toBeVisible();
    expect(within(enrichment).getByText("excerto desligado na fonte")).toBeVisible();
  });

  it("test_knowledge_tab_filters_by_status_and_confidence", async () => {
    const user = userEvent.setup();
    useKnowledgeStores();
    await renderKnowledgeTab();
    await knowledgeCard(RULE_TITLE);

    await chooseFilter(user, "Status", "Aprovado");

    const list = screen.getByRole("list", { name: ITEMS });
    expect(within(list).getAllByRole("article")).toHaveLength(1);
    expect(screen.getByText("1 item")).toBeVisible();
    expect(screen.queryByRole("article", { name: RULE_TITLE })).not.toBeInTheDocument();

    await chooseFilter(user, "Confiança", "Inferido");

    expect(screen.getByText("Nenhum item corresponde aos filtros.")).toBeVisible();

    await chooseFilter(user, "Status", "Todos os status");

    expect(await knowledgeCard(RULE_TITLE)).toBeVisible();
    expect(screen.getByText("3 itens")).toBeVisible();
  });

  it("test_knowledge_tab_switches_module", async () => {
    const user = userEvent.setup();
    const store = useKnowledgeStores();
    await renderKnowledgeTab();
    await knowledgeCard(RULE_TITLE);

    await chooseFilter(user, "Módulo", "(raiz)");

    expect(await screen.findByText(/Nenhum item de conhecimento neste módulo ainda/)).toBeVisible();
    expect(store.queries).toContain("limit=200&offset=0&module=root");
    expect(screen.getByText("Nenhuma tarefa concluída deste módulo ainda.")).toBeVisible();
  });

  it("test_knowledge_tab_without_modules_explains_where_knowledge_comes_from", async () => {
    useKnowledgeStores({}, []);
    await renderKnowledgeTab();

    expect(await screen.findByText(/O conhecimento aparece por módulo/)).toBeVisible();
    expect(screen.queryByRole("combobox", { name: "Módulo" })).not.toBeInTheDocument();
  });

  it("test_knowledge_tab_reports_a_failed_load_and_retries", async () => {
    const user = userEvent.setup();
    useKnowledgeStores();
    server.use(knowledgeServerError);
    await renderKnowledgeTab();

    expect(
      await screen.findByText("Não foi possível carregar o conhecimento do módulo."),
    ).toBeVisible();

    server.resetHandlers();
    useKnowledgeStores();
    await user.click(screen.getByRole("button", { name: "Tentar novamente" }));

    expect(await knowledgeCard(RULE_TITLE)).toBeVisible();
  });

  it("test_knowledge_tab_reports_failed_modules_and_retries", async () => {
    const user = userEvent.setup();
    useKnowledgeStores();
    server.use(harnessModulesServerError);
    renderWithProviders({ path: KNOWLEDGE_TAB_PATH });

    expect(await screen.findByText("Não foi possível carregar os módulos.")).toBeVisible();

    server.resetHandlers();
    useKnowledgeStores();
    await user.click(screen.getByRole("button", { name: "Tentar novamente" }));

    expect(await knowledgeCard(RULE_TITLE)).toBeVisible();
  });
});

describe("KnowledgeTab export and rejections", () => {
  let downloads: ReturnType<typeof stubDownloads>;

  beforeEach(() => {
    downloads = stubDownloads();
  });

  afterEach(() => {
    downloads.restore();
  });

  it("test_knowledge_tab_exports_the_module_as_a_download", async () => {
    const user = userEvent.setup();
    const store = useKnowledgeStores();
    await renderKnowledgeTab();
    await knowledgeCard(RULE_TITLE);

    await user.click(screen.getByRole("button", { name: "Exportar .md do módulo" }));

    expect(
      await screen.findByText("Download de erp-local-src-faturamento.zip iniciado."),
    ).toBeVisible();
    expect(store.exports).toEqual(["src-faturamento"]);
    expect(downloads.saved).toEqual([
      { name: "erp-local-src-faturamento.zip", href: "blob:download-1" },
    ]);
  });

  it("test_knowledge_tab_reports_a_failed_export", async () => {
    const user = userEvent.setup();
    useKnowledgeStores();
    server.use(knowledgeExportFails(404, "module_not_found"));
    await renderKnowledgeTab();
    await knowledgeCard(RULE_TITLE);

    await user.click(screen.getByRole("button", { name: "Exportar .md do módulo" }));

    expect(await screen.findByText("Módulo não encontrado. A lista foi atualizada.")).toBeVisible();
    expect(downloads.saved).toEqual([]);
  });

  it("test_knowledge_tab_shows_the_export_in_progress", async () => {
    const user = userEvent.setup();
    useKnowledgeStores();
    let finish: (response: Response) => void = () => undefined;
    server.use(
      http.get(
        "*/v1/workspaces/:workspaceId/sources/:sourceId/knowledge/export",
        () =>
          new Promise<Response>((resolve) => {
            finish = resolve;
          }),
      ),
    );
    await renderKnowledgeTab();
    await knowledgeCard(RULE_TITLE);

    await user.click(screen.getByRole("button", { name: "Exportar .md do módulo" }));

    expect(await screen.findByRole("button", { name: "Exportando…" })).toBeDisabled();
    finish(HttpResponse.json({ error: { code: "internal_error" } }, { status: 500 }));
    expect(await screen.findByRole("button", { name: "Exportar .md do módulo" })).toBeEnabled();
  });

  it("test_knowledge_tab_reads_rejections_from_the_item_job_when_jobs_fail", async () => {
    useKnowledgeStores();
    server.use(harnessJobsServerError);
    await renderKnowledgeTab();

    expect(await screen.findByRole("list", { name: "Itens rejeitados do módulo" })).toBeVisible();
  });

  it("test_knowledge_tab_lists_the_latest_job_rejections_with_reason", async () => {
    useKnowledgeStores();
    await renderKnowledgeTab();

    const rejected = await screen.findByRole("list", { name: "Itens rejeitados do módulo" });
    expect(within(rejected).getByText("Nota exige CNPJ (Regras)")).toBeVisible();
    expect(
      within(rejected).getByText("Arquivo citado não existe no checkout ou não é texto."),
    ).toBeVisible();
    expect(within(rejected).getByText("src/faturamento/nota.py:10–24")).toBeVisible();
    expect(within(rejected).getByText("Informe o CNPJ (Mensagens)")).toBeVisible();
    expect(screen.getByRole("list", { name: "Rejeições por motivo" })).toHaveTextContent(
      "Arquivo citado não existe no checkout ou não é texto. (1)",
    );
    expect(screen.getByText(/2 itens rejeitados/)).toBeVisible();
  });

  it("test_knowledge_tab_reads_rejections_from_the_item_job_when_the_job_list_misses_it", async () => {
    // The module's job is older than the loaded page of jobs: the items still name it.
    useKnowledgeStores({ jobs: [], rejections: {} });
    server.use(
      ...harnessStore(makeHarnessModules(), {
        jobs: [makeHarnessJob({ source_id: "outra-fonte" })],
        rejections: { [JOB_ID]: [] },
      }).handlers,
    );
    await renderKnowledgeTab();

    expect(await screen.findByText(/Nenhum item rejeitado/)).toBeVisible();
    expect(
      screen.queryByRole("list", { name: "Itens rejeitados do módulo" }),
    ).not.toBeInTheDocument();
  });

  it("test_knowledge_tab_reports_failed_rejections_and_retries", async () => {
    const user = userEvent.setup();
    useKnowledgeStores();
    server.use(harnessJobServerError);
    await renderKnowledgeTab();

    expect(await screen.findByText("Não foi possível carregar os rejeitados.")).toBeVisible();

    server.resetHandlers();
    useKnowledgeStores();
    const section = screen.getByRole("region", { name: "Rejeitados na última tarefa do módulo" });
    await user.click(within(section).getByRole("button", { name: "Tentar novamente" }));

    expect(await screen.findByRole("list", { name: "Itens rejeitados do módulo" })).toBeVisible();
  });
});
