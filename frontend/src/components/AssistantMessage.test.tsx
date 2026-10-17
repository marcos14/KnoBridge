import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { Citation } from "@/lib/api/conversations";
import { makeCitation } from "@/test/factories";
import { makeKnowledgeCitation } from "@/test/knowledgeFactories";
import { renderWithProviders } from "@/test/renderWithProviders";
import { makeCardCitation, makeTicketCitation } from "@/test/ticketFactories";

import { AssistantMessage } from "./AssistantMessage";

function renderAnswer(citations: Citation[], onCitation = vi.fn()) {
  renderWithProviders({
    routes: [
      {
        path: "/",
        element: (
          <AssistantMessage
            content="Veja as fontes."
            citations={citations}
            status="completed"
            errorCode={null}
            onCitation={onCitation}
          />
        ),
      },
    ],
  });
  return onCitation;
}

describe("AssistantMessage sources", () => {
  it("test_assistant_message_lists_code_and_commit_locations", async () => {
    const user = userEvent.setup();
    const code = makeCitation({
      title: "caixa.ts",
      kind: "file",
      path: "src/caixa.ts",
      start_line: 12,
      end_line: 18,
    });
    const commit = makeCitation({
      index: 2,
      title: "fix: troco",
      kind: "commit",
      sha: "9f8e7d6c5b4a39281706f5e4d3c2b1a098765432",
    });
    const onCitation = renderAnswer([code, commit]);

    const codeButton = await screen.findByRole("button", {
      name: "[1] caixa.ts src/caixa.ts:L12–L18",
    });
    expect(screen.getByRole("button", { name: "[2] fix: troco commit 9f8e7d6" })).toBeVisible();
    await user.click(codeButton);

    expect(onCitation).toHaveBeenCalledWith(code);
  });

  it("test_assistant_message_lists_legacy_sources_by_title_only", async () => {
    renderAnswer([makeCitation()]);

    expect(await screen.findByRole("button", { name: "[1] Manual do caixa" })).toBeVisible();
  });

  it("test_assistant_message_lists_knowledge_with_evidence_and_seal", async () => {
    const user = userEvent.setup();
    const knowledge = makeKnowledgeCitation({ index: 2 });
    const onCitation = renderAnswer([makeCitation(), knowledge]);

    const button = await screen.findByRole("button", {
      name: "[2] Nota fiscal exige CNPJ do cliente src/faturamento/notas.ts:L80–L92 +1 Revisado",
    });
    expect(screen.getByRole("button", { name: "[1] Manual do caixa" })).toBeVisible();
    await user.click(button);

    expect(onCitation).toHaveBeenCalledWith(knowledge);
  });

  it("test_assistant_message_lists_knowledge_without_seal_or_evidence", async () => {
    renderAnswer([makeKnowledgeCitation({ confidence: null, evidence: null })]);

    expect(
      await screen.findByRole("button", { name: "[1] Nota fiscal exige CNPJ do cliente" }),
    ).toBeVisible();
  });

  it("test_assistant_message_lists_tickets_with_number_and_status", async () => {
    const user = userEvent.setup();
    const ticket = makeTicketCitation({ index: 2 });
    const onCitation = renderAnswer([makeCitation(), ticket]);

    const button = await screen.findByRole("button", {
      name: "[2] Erro 4021 ao fechar o caixa Chamado 48213 Resolvido",
    });
    await user.click(button);

    expect(onCitation).toHaveBeenCalledWith(ticket);
  });

  it("test_assistant_message_lists_a_ticket_without_number_or_status", async () => {
    renderAnswer([makeTicketCitation({ ticket_number: null, ticket_status: null })]);

    expect(
      await screen.findByRole("button", { name: "[1] Erro 4021 ao fechar o caixa" }),
    ).toBeVisible();
  });

  it("test_assistant_message_lists_cards_with_number_and_status", async () => {
    const user = userEvent.setup();
    const card = makeCardCitation({ index: 2 });
    const onCitation = renderAnswer([makeCitation(), card]);

    const button = await screen.findByRole("button", {
      name: "[2] Fechamento do caixa trava com sangria pendente Card PROJ-123 Concluído",
    });
    await user.click(button);

    expect(onCitation).toHaveBeenCalledWith(card);
  });

  it("test_assistant_message_lists_a_card_without_number_or_status", async () => {
    renderAnswer([makeCardCitation({ card_number: null, card_status: null })]);

    expect(
      await screen.findByRole("button", {
        name: "[1] Fechamento do caixa trava com sangria pendente",
      }),
    ).toBeVisible();
  });
});

function renderSteps(props: Partial<Parameters<typeof AssistantMessage>[0]>) {
  renderWithProviders({
    routes: [
      {
        path: "/",
        element: (
          <AssistantMessage
            content=""
            citations={[]}
            status="streaming"
            errorCode={null}
            onCitation={vi.fn()}
            {...props}
          />
        ),
      },
    ],
  });
}

describe("AssistantMessage searches", () => {
  it("test_assistant_message_streaming_shows_the_search_in_progress", async () => {
    renderSteps({ searching: { query: "tabela do caixa" } });

    expect(await screen.findByText("Buscando: tabela do caixa")).toBeVisible();
    expect(screen.queryByText("O assistente está respondendo…")).not.toBeInTheDocument();
  });

  it("test_assistant_message_search_without_query_is_generic", async () => {
    renderSteps({ searching: { query: null } });

    expect(await screen.findByText("Buscando mais informações…")).toBeVisible();
  });

  it("test_assistant_message_search_gives_way_to_the_text", async () => {
    renderSteps({ content: "Abra o caixa.", searching: { query: "tabela do caixa" } });

    expect(await screen.findByText("Abra o caixa.")).toBeVisible();
    expect(screen.queryByText("Buscando: tabela do caixa")).not.toBeInTheDocument();
  });

  it("test_assistant_message_shows_the_searches_and_their_queries", async () => {
    const user = userEvent.setup();
    renderSteps({
      content: "Feito.",
      status: "completed",
      steps: 3,
      stepQueries: ["tabela do caixa", "fechamento diário"],
    });

    await user.click(await screen.findByText("3 buscas"));

    const queries = screen.getByRole("list", { name: "Buscas feitas para esta resposta" });
    expect(queries).toHaveTextContent("A perguntatabela do caixafechamento diário");
  });

  it("test_assistant_message_single_search_is_a_plain_count", async () => {
    renderSteps({ content: "Feito.", status: "completed", steps: 1 });

    expect(await screen.findByText("1 busca")).toBeVisible();
    expect(screen.queryByRole("list")).not.toBeInTheDocument();
  });

  it("test_assistant_message_without_searches_shows_no_count", async () => {
    renderSteps({ content: "Feito.", status: "completed", steps: 0 });

    await screen.findByText("Feito.");
    expect(screen.queryByText(/busca/)).not.toBeInTheDocument();
  });
});
