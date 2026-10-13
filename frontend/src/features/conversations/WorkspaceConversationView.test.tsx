import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import {
  CONVERSATION_ID,
  makeCitation,
  makeWorkspaceConversation,
  makeWorkspaceConversationDetail,
  makeWorkspaceMessage,
  messageId,
  WORKSPACE_ID,
} from "@/test/factories";
import {
  workspaceConversationAs,
  workspaceConversationServerError,
  workspaceConversationsRecorder,
} from "@/test/handlers";
import { renderWithProviders } from "@/test/renderWithProviders";
import { server } from "@/test/server";

const LIST = `/w/${WORKSPACE_ID}/conversations`;
const DETAIL = `${LIST}/${CONVERSATION_ID}`;

async function openDetail(path = DETAIL) {
  const user = userEvent.setup();
  const rendered = renderWithProviders({ path });
  await screen.findByRole("heading", { level: 1, name: "Conversas" });
  return { user, ...rendered };
}

function thread() {
  return screen.getByRole("list", { name: "Mensagens da conversa" });
}

describe("WorkspaceConversationView", () => {
  it("test_conversation_detail_opens_from_the_list_keeping_filters", async () => {
    server.use(...workspaceConversationsRecorder().handlers);
    const user = userEvent.setup();
    const { router } = renderWithProviders({ path: `${LIST}?negative=1` });

    await user.click(await screen.findByRole("link", { name: "Como fecho o caixa?" }));

    expect(
      await screen.findByRole("heading", { level: 2, name: "Como fecho o caixa?" }),
    ).toBeVisible();
    expect(router.state.location.pathname).toBe(DETAIL);
    expect(router.state.location.search).toBe("?negative=1");
    await user.click(screen.getByRole("link", { name: "Voltar para as conversas" }));

    await waitFor(() => {
      expect(router.state.location.pathname).toBe(LIST);
    });
    expect(router.state.location.search).toBe("?negative=1");
    expect(await screen.findByRole("checkbox", { name: "Só com 👎" })).toBeChecked();
  });

  it("test_conversation_detail_shows_messages_read_only", async () => {
    await openDetail();

    expect(await screen.findByText("Ana Teste (ana@example.test) com Suporte ERP")).toBeVisible();
    expect(screen.getByText(/Somente leitura/)).toBeVisible();
    expect(within(thread()).getByText("Como fecho o caixa?")).toBeVisible();
    expect(within(thread()).getByText("Fechar").tagName).toBe("STRONG");
    expect(within(thread()).getByText("E a sangria?")).toBeVisible();
    // Read only: no composer, no rating buttons, no ticket offer.
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Resposta útil" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Abrir chamado" })).not.toBeInTheDocument();
    expect(
      screen.getByText("Respondida sem fonte: o assistente ofereceu abrir chamado."),
    ).toBeVisible();
    expect(screen.getByText("Modelo gpt-4.1-mini · 1200 ms")).toBeVisible();
    expect(screen.getByText("300 ms")).toBeVisible();
  });

  it("test_conversation_detail_of_the_api_shows_the_key", async () => {
    server.use(
      workspaceConversationAs(
        makeWorkspaceConversationDetail(
          makeWorkspaceConversation({
            channel: "api",
            user_id: null,
            user_name: null,
            user_email: null,
            api_key_id: "00000000-0000-4000-8000-0000000000a1",
            api_key_name: "Integração ERP",
          }),
        ),
      ),
    );
    await openDetail();

    expect(await screen.findByText("API · Integração ERP com Suporte ERP")).toBeVisible();
    expect(within(thread()).getAllByText("Pergunta de API · Integração ERP:")).toHaveLength(2);
  });

  it("test_conversation_detail_shows_everyone_feedback", async () => {
    await openDetail();

    const ratings = await screen.findAllByRole("list", { name: "Avaliações da resposta" });
    expect(ratings.map((list) => list.textContent)).toEqual([
      "👍 Ana TesteResolveu.",
      "👎 Bruno LimaFaltou o manual.",
    ]);
  });

  it("test_conversation_detail_citation_opens_the_source", async () => {
    const { user } = await openDetail();

    await user.click(await screen.findByRole("button", { name: "Fonte 1: Manual do caixa" }));

    const panel = await screen.findByRole("dialog", { name: "[1] Manual do caixa" });
    expect(within(panel).getByText(makeCitation().snippet)).toBeVisible();
    await user.click(within(panel).getByRole("button", { name: "Fechar" }));
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
  });

  it("test_conversation_detail_marks_failed_and_interrupted_answers", async () => {
    server.use(
      workspaceConversationAs(
        makeWorkspaceConversationDetail(makeWorkspaceConversation({ title: null }), [
          makeWorkspaceMessage({
            id: messageId(2),
            content: "",
            status: "failed",
            error_code: "provider_rate_limited",
            model: null,
            latency_ms: null,
          }),
          makeWorkspaceMessage({ id: messageId(4), content: "Parcial", status: "interrupted" }),
        ]),
      ),
    );
    await openDetail();

    expect(
      await screen.findByRole("heading", { level: 2, name: "Conversa sem título" }),
    ).toBeVisible();
    expect(
      screen.getByText(
        "O provedor de LLM atingiu o limite de uso. Aguarde um pouco e tente de novo.",
      ),
    ).toBeVisible();
    expect(screen.getByText("A resposta foi interrompida antes do fim.")).toBeVisible();
    expect(screen.queryByRole("button", { name: "Reenviar pergunta" })).not.toBeInTheDocument();
  });

  it("test_conversation_detail_without_messages_says_so", async () => {
    server.use(
      workspaceConversationAs(makeWorkspaceConversationDetail(makeWorkspaceConversation(), [])),
    );
    await openDetail();

    expect(await screen.findByText("Esta conversa ainda não tem mensagens.")).toBeVisible();
  });

  it("test_conversation_detail_unknown_conversation_is_not_found", async () => {
    await openDetail(`${LIST}/00000000-0000-4000-8000-00000000dead`);

    expect(
      await screen.findByRole("heading", { level: 2, name: "Conversa não encontrada" }),
    ).toBeVisible();
  });

  it("test_conversation_detail_load_failure_offers_retry", async () => {
    server.use(workspaceConversationServerError);
    const { user } = await openDetail();

    expect(await screen.findByText("Não foi possível carregar a conversa.")).toBeVisible();
    server.use(workspaceConversationAs());
    await user.click(screen.getByRole("button", { name: "Tentar novamente" }));

    expect(
      await screen.findByRole("heading", { level: 2, name: "Como fecho o caixa?" }),
    ).toBeVisible();
  });
});
