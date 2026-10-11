import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { controlledReview, knowledgeReviewFails } from "@/test/handlers";
import { makeKnowledgeItems, makeRuleItem } from "@/test/knowledgeFactories";
import {
  APPROVED_TITLE,
  knowledgeAsRole,
  knowledgeCard,
  renderKnowledgeTab,
  RULE_TITLE,
  useKnowledgeStores,
} from "@/test/knowledgeTab";
import { server } from "@/test/server";

// Review actions and edits of the Knowledge tab; the list, filters, export and rejections live
// in KnowledgeTab.test.tsx.
describe("KnowledgeTab review", () => {
  it("test_knowledge_tab_approves_optimistically", async () => {
    const user = userEvent.setup();
    useKnowledgeStores();
    const review = controlledReview();
    server.use(review.handler);
    await renderKnowledgeTab();
    const rule = await knowledgeCard(RULE_TITLE);

    await user.click(within(rule).getByRole("button", { name: `Aprovar ${RULE_TITLE}` }));

    // Before the server answers, the list already shows the approved item.
    expect(await within(rule).findByText("Revisado")).toBeVisible();
    expect(within(rule).getByText("Aprovado")).toBeVisible();
    expect(
      within(rule).queryByRole("button", { name: `Aprovar ${RULE_TITLE}` }),
    ).not.toBeInTheDocument();
    await waitFor(() => {
      expect(review.bodies).toEqual([{ action: "approve" }]);
    });

    review.respond(makeRuleItem({ review_status: "approved", confidence: "revisado" }));

    expect(
      await screen.findByText(`${RULE_TITLE} aprovado: o selo agora é revisado.`),
    ).toBeVisible();
  });

  it("test_knowledge_tab_rolls_back_a_refused_discard", async () => {
    const user = userEvent.setup();
    useKnowledgeStores();
    const review = controlledReview();
    server.use(review.handler);
    await renderKnowledgeTab();
    const rule = await knowledgeCard(RULE_TITLE);

    await user.click(within(rule).getByRole("button", { name: `Descartar ${RULE_TITLE}` }));
    expect(await within(rule).findByText("Descartado")).toBeVisible();

    review.fail(404, "knowledge_item_not_found");

    expect(
      await screen.findByText("Item de conhecimento não encontrado. A lista foi atualizada."),
    ).toBeVisible();
    expect(await within(rule).findByText("Pendente")).toBeVisible();
    expect(within(rule).queryByText("Descartado")).not.toBeInTheDocument();
  });

  it("test_knowledge_tab_reopens_an_approved_item", async () => {
    const user = userEvent.setup();
    const store = useKnowledgeStores();
    await renderKnowledgeTab();
    const approved = await knowledgeCard(APPROVED_TITLE);

    await user.click(within(approved).getByRole("button", { name: `Reabrir ${APPROVED_TITLE}` }));

    expect(await screen.findByText(`${APPROVED_TITLE} reaberto para revisão.`)).toBeVisible();
    expect(within(approved).getByText("Pendente")).toBeVisible();
    expect(within(approved).getByText("Inferido")).toBeVisible();
    expect(store.changes).toEqual([
      { itemId: makeKnowledgeItems()[1]?.id, body: { action: "reopen" } },
    ]);
  });

  it("test_knowledge_tab_discards_with_the_store", async () => {
    const user = userEvent.setup();
    useKnowledgeStores();
    await renderKnowledgeTab();
    const rule = await knowledgeCard(RULE_TITLE);

    await user.click(within(rule).getByRole("button", { name: `Descartar ${RULE_TITLE}` }));

    expect(
      await screen.findByText(`${RULE_TITLE} descartado: sai do índice na próxima sincronização.`),
    ).toBeVisible();
    expect(within(rule).getByRole("button", { name: `Reabrir ${RULE_TITLE}` })).toBeVisible();
  });

  it("test_knowledge_tab_viewer_reads_and_exports_without_review_actions", async () => {
    knowledgeAsRole("viewer");
    useKnowledgeStores();
    await renderKnowledgeTab();
    const rule = await knowledgeCard(RULE_TITLE);

    expect(within(rule).queryByRole("button")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Exportar .md do módulo" })).toBeEnabled();
  });
});

describe("KnowledgeTab edit", () => {
  it("test_knowledge_tab_edits_a_rule", async () => {
    const user = userEvent.setup();
    const store = useKnowledgeStores();
    await renderKnowledgeTab();
    const rule = await knowledgeCard(RULE_TITLE);

    await user.click(within(rule).getByRole("button", { name: `Editar ${RULE_TITLE}` }));
    const dialog = await screen.findByRole("dialog", { name: "Editar regra" });
    const resolution = within(dialog).getByLabelText("Como o usuário resolve");
    await user.clear(resolution);
    await user.type(resolution, "Pedir ao financeiro o CNPJ.");
    await user.click(within(dialog).getByRole("radio", { name: "baixa" }));
    await user.click(within(dialog).getByRole("button", { name: "Salvar" }));

    expect(await screen.findByText(`${RULE_TITLE} salvo.`)).toBeVisible();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(within(rule).getByText("Pedir ao financeiro o CNPJ.")).toBeVisible();
    expect(within(rule).getByText("Editado")).toBeVisible();
    expect(store.changes[0]?.body).toEqual({
      content: {
        enunciado: "A nota só é emitida se o cliente tiver CNPJ válido.",
        quando: "Ao emitir a nota de um pedido.",
        mensagem: "Informe o CNPJ do cliente antes de emitir a nota.",
        resolucao: "Pedir ao financeiro o CNPJ.",
        parametros: ["NOTAS_SERIE_PADRAO"],
        classificacao: "intencional",
        relevancia: "baixa",
      },
    });
  });

  it("test_knowledge_tab_edit_without_changes_sends_nothing", async () => {
    const user = userEvent.setup();
    const store = useKnowledgeStores();
    await renderKnowledgeTab();
    const rule = await knowledgeCard(RULE_TITLE);

    await user.click(within(rule).getByRole("button", { name: `Editar ${RULE_TITLE}` }));
    const dialog = await screen.findByRole("dialog", { name: "Editar regra" });
    await user.click(within(dialog).getByRole("button", { name: "Salvar" }));

    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
    expect(store.changes).toEqual([]);
  });

  it("test_knowledge_tab_edit_validates_the_title", async () => {
    const user = userEvent.setup();
    const store = useKnowledgeStores();
    await renderKnowledgeTab();
    const rule = await knowledgeCard(RULE_TITLE);

    await user.click(within(rule).getByRole("button", { name: `Editar ${RULE_TITLE}` }));
    const dialog = await screen.findByRole("dialog", { name: "Editar regra" });
    await user.clear(within(dialog).getByLabelText("Título"));
    await user.click(within(dialog).getByRole("button", { name: "Salvar" }));

    expect(await within(dialog).findByText("Informe o título.")).toBeVisible();
    expect(store.changes).toEqual([]);
  });

  it("test_knowledge_tab_edit_shows_the_fields_the_server_refused", async () => {
    const user = userEvent.setup();
    useKnowledgeStores();
    server.use(
      knowledgeReviewFails(422, "knowledge_content_invalid", [
        {
          loc: ["body", "content", "quando"],
          problem: "String should have at most 1000 characters",
        },
      ]),
    );
    await renderKnowledgeTab();
    const rule = await knowledgeCard(RULE_TITLE);

    await user.click(within(rule).getByRole("button", { name: `Editar ${RULE_TITLE}` }));
    const dialog = await screen.findByRole("dialog", { name: "Editar regra" });
    await user.type(within(dialog).getByLabelText("Quando"), " Sempre.");
    await user.click(within(dialog).getByRole("button", { name: "Salvar" }));

    expect(
      await within(dialog).findByText(
        "O conteúdo editado não segue o formato do item. Confira os campos apontados.",
      ),
    ).toBeVisible();
    const problems = within(dialog).getByRole("list", { name: "Campos recusados pelo servidor" });
    expect(problems).toHaveTextContent("quando: String should have at most 1000 characters");
    // The optimistic edit went back.
    expect(within(rule).getByText("Ao emitir a nota de um pedido.")).toBeVisible();
    expect(within(rule).queryByText("Editado")).not.toBeInTheDocument();
  });

  it("test_knowledge_tab_edits_the_module_enrichment", async () => {
    const user = userEvent.setup();
    const store = useKnowledgeStores();
    await renderKnowledgeTab();
    const enrichment = await knowledgeCard("src/faturamento");

    await user.click(within(enrichment).getByRole("button", { name: "Editar src/faturamento" }));
    const dialog = await screen.findByRole("dialog", { name: "Editar módulo" });
    expect(within(dialog).getByLabelText("Mensagem 1")).toHaveValue(
      "Informe o CNPJ do cliente antes de emitir a nota.",
    );
    expect(within(dialog).getByLabelText("Resposta 1")).toHaveValue("Falta o CNPJ.");
    expect(within(dialog).getByLabelText("Contexto 1")).toHaveValue("Há um ramo sem tratamento.");
    const step = within(dialog).getByLabelText("Passo 1");
    await user.clear(step);
    await user.type(step, "Abrir o pedido já faturado.");
    await user.click(within(dialog).getByRole("button", { name: "Salvar" }));

    expect(await screen.findByText("src/faturamento salvo.")).toBeVisible();
    expect(within(enrichment).getByText("Abrir o pedido já faturado.")).toBeVisible();
    expect(store.changes[0]?.body.content).toMatchObject({
      fluxo_principal: [{ ordem: 1, passo: "Abrir o pedido já faturado.", evidencias: [0] }],
    });
  });
});
