import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import type { Role } from "@/lib/api/auth";
import {
  ASSISTANT_ID,
  CONVERSATION_ID,
  makeAssistant,
  makeAssistants,
  makeCitation,
  makeConversation,
  makeConversationDetail,
  makeMe,
  makeMessage,
  makeQuestion,
  makeThread,
  makeWorkspace,
  messageId,
  OTHER_ASSISTANT_ID,
  OTHER_CONVERSATION_ID,
  WORKSPACE_ID,
} from "@/test/factories";
import {
  answerFrames,
  apiErrorResponse,
  assistantsAs,
  assistantsServerError,
  chatStore,
  controlledStream,
  conversationServerError,
  conversationsServerError,
  createConversationFails,
  deleteConversationFails,
  exchangeIds,
  feedbackFails,
  meAs,
  messagesRespond,
  savedAnswer,
} from "@/test/handlers";
import { renderWithProviders } from "@/test/renderWithProviders";
import { server } from "@/test/server";

const CHAT = `/w/${WORKSPACE_ID}/chat`;
const NEW_CONVERSATION_ID = "00000000-0000-4000-8000-000000000990";

function asRole(role: Role) {
  server.use(meAs(makeMe({ workspaces: [makeWorkspace({ role })] })));
}

function useStore(options: Parameters<typeof chatStore>[0] = {}) {
  const store = chatStore({ messages: { [CONVERSATION_ID]: makeThread() }, ...options });
  server.use(...store.handlers);
  return store;
}

async function openChat(path = CHAT) {
  const user = userEvent.setup();
  const rendered = renderWithProviders({ path });
  await screen.findByRole("heading", { level: 1, name: "Chat" });
  return { user, ...rendered };
}

function composer() {
  return screen.getByRole("textbox", { name: "Sua pergunta" });
}

describe("ChatPage", () => {
  it("test_chat_viewer_sees_conversations_and_active_assistants", async () => {
    asRole("viewer");
    useStore();
    // The API lists only active assistants to viewers.
    server.use(assistantsAs([makeAssistant()]));
    await openChat();

    const list = screen.getByRole("navigation", { name: "Suas conversas" });
    expect(await within(list).findByRole("link", { name: "Como fecho o caixa?" })).toBeVisible();
    expect(within(list).getByRole("link", { name: "Emissão de nota fiscal" })).toBeVisible();
    expect(await screen.findByRole("combobox", { name: "Assistente" })).toHaveTextContent(
      "Suporte ERP",
    );
    await waitFor(() => {
      expect(composer()).toHaveFocus();
    });
  });

  it("test_chat_starts_a_conversation_and_streams_the_answer", async () => {
    const source = controlledStream();
    const store = useStore({
      reply: () => ({
        body: source.stream,
        saved: savedAnswer("completed", "Clique em **Fechar**."),
      }),
    });
    const { user, router } = await openChat();
    await screen.findByRole("combobox", { name: "Assistente" });

    await user.type(composer(), "Como fecho o caixa?{Enter}");

    await waitFor(() => {
      expect(router.state.location.pathname).toBe(`${CHAT}/${NEW_CONVERSATION_ID}`);
    });
    expect(store.created).toEqual([makeAssistant().id]);
    expect(await screen.findByText("O assistente está respondendo…")).toBeVisible();
    expect(screen.getByRole("button", { name: "Parar" })).toBeVisible();
    const [citations, first, second, done] = answerFrames({
      ...exchangeIds(1),
      deltas: ["Clique em ", "**Fechar**."],
    });
    act(() => {
      source.push(`${citations ?? ""}${first ?? ""}`);
    });
    const live = await screen.findByText("Clique em");
    expect(live.closest("[aria-live='polite']")).not.toBeNull();
    act(() => {
      source.push(second ?? "");
    });
    expect(await screen.findByText("Fechar")).toBeVisible();
    act(() => {
      source.push(done ?? "");
      source.close();
    });

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Enviar" })).toBeVisible();
    });
    expect(store.questions).toEqual([
      { conversationId: NEW_CONVERSATION_ID, content: "Como fecho o caixa?" },
    ]);
    expect(screen.getByRole("heading", { level: 2, name: "Como fecho o caixa?" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Resposta útil" })).toBeVisible();
    expect(screen.getByText("Fechar").closest("[aria-live='polite']")).toBeNull();
  });

  it("test_chat_new_conversation_reload_before_citations_shows_question_once", async () => {
    const source = controlledStream();
    // The server saves the question and the start of the answer before the first byte.
    useStore({ reply: () => ({ body: source.stream, saved: savedAnswer("streaming", "") }) });
    const { user } = await openChat();
    await screen.findByRole("combobox", { name: "Assistente" });

    await user.type(composer(), "Como fecho o caixa?{Enter}");

    // The new conversation is read (title included) while no event has arrived yet.
    expect(
      await screen.findByRole("heading", { level: 2, name: "Como fecho o caixa?" }),
    ).toBeVisible();
    const thread = screen.getByRole("list", { name: "Mensagens da conversa" });
    expect(within(thread).getAllByText("Como fecho o caixa?")).toHaveLength(1);
    expect(screen.getAllByText("O assistente está respondendo…")).toHaveLength(1);
    act(() => {
      source.push(answerFrames({ ...exchangeIds(1) })[0] ?? "");
    });
    await waitFor(() => {
      expect(within(thread).getAllByText("Como fecho o caixa?")).toHaveLength(1);
    });
  });

  it("test_chat_new_conversation_title_shows_when_first_load_ends_after_the_answer", async () => {
    const source = controlledStream();
    useStore({ reply: () => ({ body: source.stream }) });
    // The first read of the new conversation is taken before the question names it and only
    // arrives after the answer ended; the reload at the end must not reuse it.
    let release!: () => void;
    const held = new Promise<void>((resolve) => {
      release = resolve;
    });
    let firstRead = false;
    server.use(
      http.get(`*/v1/workspaces/:workspaceId/conversations/${NEW_CONVERSATION_ID}`, async () => {
        if (firstRead) {
          return undefined;
        }
        firstRead = true;
        const untitled = makeConversation({
          id: NEW_CONVERSATION_ID,
          product_id: ASSISTANT_ID,
          title: null,
        });
        await held;
        return HttpResponse.json(makeConversationDetail(untitled, []));
      }),
    );
    const { user } = await openChat();
    await screen.findByRole("combobox", { name: "Assistente" });

    await user.type(composer(), "Como fecho o caixa?{Enter}");
    await waitFor(() => {
      expect(firstRead).toBe(true);
    });
    act(() => {
      source.push(answerFrames({ ...exchangeIds(1), deltas: ["Resposta."] }).join(""));
      source.close();
    });
    const list = screen.getByRole("navigation", { name: "Suas conversas" });
    await waitFor(() => {
      expect(within(list).getAllByRole("link", { name: "Como fecho o caixa?" })).toHaveLength(2);
    });
    act(() => {
      release();
    });

    expect(
      await screen.findByRole("heading", { level: 2, name: "Como fecho o caixa?" }),
    ).toBeVisible();
    expect(screen.queryByRole("heading", { level: 2, name: "Conversa sem título" })).toBeNull();
  });

  it("test_chat_starts_with_the_chosen_assistant", async () => {
    asRole("editor");
    const store = useStore();
    server.use(
      assistantsAs([
        ...makeAssistants(),
        makeAssistant({ id: OTHER_ASSISTANT_ID, name: "Fiscal", description: "" }),
      ]),
    );
    const { user } = await openChat();

    await user.click(await screen.findByRole("combobox", { name: "Assistente" }));
    // The inactive "Rascunho" is not offered.
    expect(screen.queryByRole("option", { name: "Rascunho" })).not.toBeInTheDocument();
    await user.click(await screen.findByRole("option", { name: "Fiscal" }));
    await user.type(composer(), "Nota?{Enter}");

    await waitFor(() => {
      expect(store.created).toEqual([OTHER_ASSISTANT_ID]);
    });
  });

  it("test_chat_create_failure_gives_the_question_back", async () => {
    useStore();
    server.use(createConversationFails(409, "assistant_inactive"));
    const { user } = await openChat();
    await screen.findByRole("combobox", { name: "Assistente" });

    await user.type(composer(), "Pergunta{Enter}");

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Este assistente está inativo e não aceita novas mensagens.",
    );
    expect(composer()).toHaveValue("Pergunta");
  });

  it("test_chat_composer_validates_and_shift_enter_breaks_line", async () => {
    const store = useStore();
    const { user } = await openChat(`${CHAT}/${CONVERSATION_ID}`);
    await screen.findByText(/Confira os lançamentos/);

    await user.click(screen.getByRole("button", { name: "Enviar" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Escreva uma pergunta.");
    await user.type(composer(), "linha 1{Shift>}{Enter}{/Shift}linha 2");

    expect(composer()).toHaveValue("linha 1\nlinha 2");
    expect(store.questions).toEqual([]);
  });

  it("test_chat_citations_open_the_source_panel", async () => {
    useStore();
    const { user } = await openChat(`${CHAT}/${CONVERSATION_ID}`);

    await user.click(await screen.findByRole("button", { name: "Fonte 1: Manual do caixa" }));

    const panel = await screen.findByRole("dialog", { name: "[1] Manual do caixa" });
    expect(within(panel).getByText(makeCitation().snippet)).toBeVisible();
    const link = within(panel).getByRole("link", { name: "Abrir a fonte" });
    expect(link).toHaveAttribute("href", "https://docs.example.test/caixa");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
    await user.click(within(panel).getByRole("button", { name: "Fechar" }));
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: "[1] Manual do caixa" }));
    expect(await screen.findByRole("dialog")).toBeVisible();
  });

  it("test_chat_source_without_web_address_shows_its_path", async () => {
    useStore({
      messages: {
        [CONVERSATION_ID]: [
          makeQuestion("Onde?"),
          makeMessage({
            content: "Em src/caixa.py [1].",
            citations: [makeCitation({ title: "caixa.py", uri: "src/caixa.py" })],
          }),
        ],
      },
    });
    const { user } = await openChat(`${CHAT}/${CONVERSATION_ID}`);

    await user.click(await screen.findByRole("button", { name: "Fonte 1: caixa.py" }));

    const panel = await screen.findByRole("dialog");
    expect(within(panel).getByText("src/caixa.py")).toBeVisible();
    expect(within(panel).queryByRole("link")).not.toBeInTheDocument();
  });

  it("test_chat_code_citation_shows_path_lines_and_code", async () => {
    useStore({
      messages: {
        [CONVERSATION_ID]: [
          makeQuestion("Onde fecha o caixa?"),
          makeMessage({
            content: "Em fecharCaixa [1].",
            citations: [
              makeCitation({
                title: "caixa.ts",
                uri: "src/caixa.ts#L12-L18",
                snippet: "export function fecharCaixa() {}",
                kind: "file",
                path: "src/caixa.ts",
                symbol: "fecharCaixa",
                start_line: 12,
                end_line: 18,
                language: "typescript",
              }),
            ],
          }),
        ],
      },
    });
    const { user } = await openChat(`${CHAT}/${CONVERSATION_ID}`);

    await user.click(await screen.findByRole("button", { name: /src\/caixa\.ts:L12–L18/ }));

    const panel = await screen.findByRole("dialog", { name: "[1] caixa.ts" });
    expect(within(panel).getByText("L12–L18")).toBeVisible();
    expect(
      within(panel).getByText("export function fecharCaixa() {}", { selector: "code" }),
    ).toHaveClass("language-typescript");
  });

  const NO_COLLECTIONS_HINT =
    "Este assistente ainda não usa nenhuma coleção: responderá sempre sem fonte.";

  it("test_chat_hints_when_the_chosen_assistant_has_no_collection", async () => {
    useStore();
    server.use(
      assistantsAs([
        makeAssistant(),
        makeAssistant({ id: OTHER_ASSISTANT_ID, name: "Fiscal", collection_ids: [] }),
      ]),
    );
    const { user } = await openChat();

    await screen.findByRole("combobox", { name: "Assistente" });
    expect(screen.queryByText(NO_COLLECTIONS_HINT)).not.toBeInTheDocument();
    await user.click(screen.getByRole("combobox", { name: "Assistente" }));
    await user.click(await screen.findByRole("option", { name: "Fiscal" }));

    expect(screen.getByText(NO_COLLECTIONS_HINT)).toBeVisible();
  });

  it("test_chat_conversation_hints_when_its_assistant_has_no_collection", async () => {
    useStore();
    server.use(assistantsAs([makeAssistant({ collection_ids: [] })]));
    await openChat(`${CHAT}/${CONVERSATION_ID}`);

    expect(await screen.findByText(NO_COLLECTIONS_HINT)).toBeVisible();
  });

  it("test_chat_no_source_answer_offers_no_ticket_without_the_webhook", async () => {
    const store = useStore({
      reply: () => ({
        body: answerFrames({
          ...exchangeIds(1),
          deltas: ["Não encontrei isso nas fontes."],
          end: { status: "no_source" },
        }).join(""),
        saved: savedAnswer("no_source", "Não encontrei isso nas fontes.", { model: null }),
      }),
    });
    const { user } = await openChat(`${CHAT}/${CONVERSATION_ID}`);
    await screen.findByText(/Confira os lançamentos/);

    await user.type(composer(), "Qual a cor do céu?{Enter}");

    expect(await screen.findByText("Não encontrei isso nas fontes.")).toBeVisible();
    await waitFor(() => {
      expect(screen.queryByRole("button", { name: "Parar" })).not.toBeInTheDocument();
    });
    expect(screen.queryByRole("button", { name: /Abrir chamado/ })).not.toBeInTheDocument();
    expect(store.ticketPreviews).toEqual([]);
  });

  it("test_chat_failed_answer_can_be_resent", async () => {
    const store = useStore({
      messages: {
        [CONVERSATION_ID]: [
          makeQuestion("Como fecho o caixa?"),
          makeMessage({ content: "", status: "failed", error_code: "provider_rate_limited" }),
        ],
      },
    });
    const { user } = await openChat(`${CHAT}/${CONVERSATION_ID}`);

    expect(
      await screen.findByText(
        "O provedor de LLM atingiu o limite de uso. Aguarde um pouco e tente de novo.",
      ),
    ).toBeVisible();
    expect(screen.queryByRole("button", { name: "Resposta útil" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Reenviar pergunta" }));

    await waitFor(() => {
      expect(store.questions).toEqual([
        { conversationId: CONVERSATION_ID, content: "Como fecho o caixa?" },
      ]);
    });
  });

  it("test_chat_interrupted_and_streaming_answers_are_marked", async () => {
    useStore({
      messages: {
        [CONVERSATION_ID]: [
          makeQuestion("Primeira", messageId(1)),
          makeMessage({ id: messageId(2), content: "Parcial", status: "interrupted" }),
          makeQuestion("Segunda", messageId(3)),
          makeMessage({ id: messageId(4), content: "", status: "streaming" }),
          makeMessage({ id: messageId(5), content: "", status: "failed", error_code: null }),
        ],
      },
    });
    await openChat(`${CHAT}/${CONVERSATION_ID}`);

    expect(await screen.findByText("A resposta foi interrompida antes do fim.")).toBeVisible();
    expect(screen.getByText("Parcial")).toBeVisible();
    expect(screen.getByText("O assistente está respondendo…")).toBeVisible();
    expect(screen.getByText("O assistente não conseguiu responder. Tente de novo.")).toBeVisible();
    expect(screen.getAllByRole("button", { name: "Reenviar pergunta" })).toHaveLength(2);
  });

  it("test_chat_stop_ends_the_answer_and_reloads", async () => {
    const source = controlledStream();
    useStore({
      reply: () => ({ body: source.stream, saved: savedAnswer("interrupted", "Começo") }),
    });
    const { user } = await openChat(`${CHAT}/${CONVERSATION_ID}`);
    await screen.findByText(/Confira os lançamentos/);
    await user.type(composer(), "Outra{Enter}");
    const [citations, delta] = answerFrames({ ...exchangeIds(1), deltas: ["Começo"] });
    act(() => {
      source.push(`${citations ?? ""}${delta ?? ""}`);
    });
    await screen.findByText("Começo");

    await user.click(screen.getByRole("button", { name: "Parar" }));

    expect(await screen.findByText("A resposta foi interrompida antes do fim.")).toBeVisible();
    expect(screen.getByRole("button", { name: "Enviar" })).toBeVisible();
    await waitFor(() => {
      expect(composer()).toHaveFocus();
    });
  });

  it("test_chat_json_error_before_the_stream_keeps_the_question", async () => {
    useStore();
    server.use(messagesRespond(() => apiErrorResponse(403, "forbidden")));
    const { user } = await openChat(`${CHAT}/${CONVERSATION_ID}`);
    await screen.findByText(/Confira os lançamentos/);

    await user.type(composer(), "Posso?{Enter}");

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Você não tem permissão para fazer isso.",
    );
    expect(composer()).toHaveValue("Posso?");
  });

  it("test_chat_send_error_clears_when_leaving_the_conversation", async () => {
    useStore();
    server.use(messagesRespond(() => apiErrorResponse(403, "forbidden")));
    const { user } = await openChat(`${CHAT}/${CONVERSATION_ID}`);
    await screen.findByText(/Confira os lançamentos/);
    await user.type(composer(), "Posso?{Enter}");
    expect(await screen.findByRole("alert")).toBeVisible();

    await user.click(screen.getByRole("link", { name: "Emissão de nota fiscal" }));
    await screen.findByRole("heading", { level: 2, name: "Emissão de nota fiscal" });
    await user.click(screen.getByRole("link", { name: "Como fecho o caixa?" }));

    expect(await screen.findByText(/Confira os lançamentos/)).toBeVisible();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("test_chat_feedback_rates_and_comments", async () => {
    const store = useStore();
    const { user } = await openChat(`${CHAT}/${CONVERSATION_ID}`);

    await user.click(await screen.findByRole("button", { name: "Resposta não ajudou" }));

    expect(await screen.findByText("Obrigado pela avaliação.")).toHaveAttribute("role", "status");
    expect(screen.getByRole("button", { name: "Resposta não ajudou" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await user.click(screen.getByRole("button", { name: "Adicionar comentário" }));
    const comment = screen.getByRole("textbox", { name: "Comentário (opcional)" });
    await waitFor(() => {
      expect(comment).toHaveFocus();
    });
    await user.type(comment, "Faltou o passo 2.");
    await user.click(screen.getByRole("button", { name: "Salvar comentário" }));

    await waitFor(() => {
      expect(store.feedback).toHaveLength(2);
    });
    expect(store.feedback).toEqual([
      { messageId: messageId(2), body: { rating: "down", comment: "" } },
      { messageId: messageId(2), body: { rating: "down", comment: "Faltou o passo 2." } },
    ]);
    expect(await screen.findByRole("button", { name: "Editar comentário" })).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Resposta útil" }));
    await waitFor(() => {
      expect(store.feedback.at(-1)).toEqual({
        messageId: messageId(2),
        body: { rating: "up", comment: "Faltou o passo 2." },
      });
    });
  });

  it("test_chat_feedback_comment_can_be_cancelled_and_validated", async () => {
    useStore({
      messages: {
        [CONVERSATION_ID]: [
          makeQuestion("Oi"),
          makeMessage({
            feedback: { rating: "up", comment: "", updated_at: "2026-10-10T11:00:00Z" },
          }),
        ],
      },
    });
    const { user } = await openChat(`${CHAT}/${CONVERSATION_ID}`);

    await user.click(await screen.findByRole("button", { name: "Adicionar comentário" }));
    const comment = screen.getByRole("textbox", { name: "Comentário (opcional)" });
    await user.click(comment);
    await user.paste("a".repeat(2001));
    await user.click(screen.getByRole("button", { name: "Salvar comentário" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "O comentário pode ter até 2000 caracteres.",
    );
    await user.click(screen.getByRole("button", { name: "Cancelar" }));

    expect(
      screen.queryByRole("textbox", { name: "Comentário (opcional)" }),
    ).not.toBeInTheDocument();
  });

  it("test_chat_feedback_failure_is_reported", async () => {
    useStore();
    server.use(feedbackFails(422, "feedback_target_invalid"));
    const { user } = await openChat(`${CHAT}/${CONVERSATION_ID}`);

    await user.click(await screen.findByRole("button", { name: "Resposta útil" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Só é possível avaliar respostas do assistente.",
    );
  });

  it("test_chat_deletes_the_open_conversation", async () => {
    const store = useStore();
    const { user, router } = await openChat(`${CHAT}/${CONVERSATION_ID}`);
    await screen.findByText(/Confira os lançamentos/);

    await user.click(
      screen.getByRole("button", { name: "Excluir a conversa Como fecho o caixa?" }),
    );
    const dialog = await screen.findByRole("alertdialog");
    await user.click(within(dialog).getByRole("button", { name: "Excluir" }));

    await waitFor(() => {
      expect(router.state.location.pathname).toBe(CHAT);
    });
    expect(store.deleted).toEqual([CONVERSATION_ID]);
    await waitFor(() => {
      expect(screen.queryByRole("link", { name: "Como fecho o caixa?" })).not.toBeInTheDocument();
    });
  });

  it("test_chat_deleting_another_conversation_stays_put", async () => {
    const store = useStore();
    const { user, router } = await openChat(`${CHAT}/${CONVERSATION_ID}`);
    await screen.findByText(/Confira os lançamentos/);

    await user.click(
      screen.getByRole("button", { name: "Excluir a conversa Emissão de nota fiscal" }),
    );
    await user.click(
      within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Excluir" }),
    );

    await waitFor(() => {
      expect(store.deleted).toEqual([OTHER_CONVERSATION_ID]);
    });
    expect(router.state.location.pathname).toBe(`${CHAT}/${CONVERSATION_ID}`);
  });

  it("test_chat_delete_failure_is_reported", async () => {
    useStore();
    server.use(deleteConversationFails(403, "forbidden"));
    const { user } = await openChat(`${CHAT}/${CONVERSATION_ID}`);
    await screen.findByText(/Confira os lançamentos/);

    await user.click(
      screen.getByRole("button", { name: "Excluir a conversa Como fecho o caixa?" }),
    );
    await user.click(
      within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Excluir" }),
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Você não tem permissão para fazer isso.",
    );
  });

  it("test_chat_deleting_the_streaming_conversation_stops_it", async () => {
    const source = controlledStream();
    const store = useStore({ reply: () => ({ body: source.stream }) });
    const { user, router } = await openChat(`${CHAT}/${CONVERSATION_ID}`);
    await screen.findByText(/Confira os lançamentos/);
    await user.type(composer(), "Outra{Enter}");
    await screen.findByRole("button", { name: "Parar" });

    await user.click(
      screen.getByRole("button", { name: "Excluir a conversa Como fecho o caixa?" }),
    );
    await user.click(
      within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Excluir" }),
    );

    await waitFor(() => {
      expect(router.state.location.pathname).toBe(CHAT);
    });
    expect(store.deleted).toEqual([CONVERSATION_ID]);
  });

  it("test_chat_opening_another_conversation_stops_the_answer", async () => {
    const source = controlledStream();
    useStore({ reply: () => ({ body: source.stream, saved: savedAnswer("interrupted", "") }) });
    const { user } = await openChat(`${CHAT}/${CONVERSATION_ID}`);
    await screen.findByText(/Confira os lançamentos/);
    await user.type(composer(), "Outra{Enter}");
    await screen.findByRole("button", { name: "Parar" });

    await user.click(screen.getByRole("link", { name: "Emissão de nota fiscal" }));

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Enviar" })).toBeVisible();
    });
    expect(screen.queryByText("Outra")).toBeNull();
  });

  it("test_chat_without_active_assistant_guides_the_member", async () => {
    asRole("viewer");
    useStore();
    server.use(assistantsAs([]));
    await openChat();

    expect(
      await screen.findByRole("heading", { name: "Nenhum assistente disponível" }),
    ).toBeVisible();
    expect(screen.getByText(/Peça a um administrador/)).toBeVisible();
    expect(screen.queryByRole("link", { name: "Configurar assistentes" })).not.toBeInTheDocument();
  });

  it("test_chat_without_active_assistant_links_managers_to_assistants", async () => {
    asRole("editor");
    useStore();
    server.use(assistantsAs([makeAssistant({ active: false })]));
    await openChat();

    expect(await screen.findByRole("link", { name: "Configurar assistentes" })).toHaveAttribute(
      "href",
      `/w/${WORKSPACE_ID}/assistants`,
    );
  });

  it("test_chat_load_failures_offer_retry", async () => {
    server.use(conversationsServerError, assistantsServerError);
    const { user } = await openChat();

    expect(await screen.findByText("Não foi possível carregar as conversas.")).toBeVisible();
    expect(await screen.findByText("Não foi possível carregar os assistentes.")).toBeVisible();
    useStore();
    server.use(assistantsAs());
    for (const button of screen.getAllByRole("button", { name: "Tentar de novo" })) {
      await user.click(button);
    }

    expect(await screen.findByRole("link", { name: "Como fecho o caixa?" })).toBeVisible();
    expect(await screen.findByRole("combobox", { name: "Assistente" })).toBeVisible();
  });

  it("test_chat_conversation_load_failure_offers_retry", async () => {
    useStore();
    server.use(conversationServerError);
    const { user } = await openChat(`${CHAT}/${CONVERSATION_ID}`);

    expect(await screen.findByText("Não foi possível carregar a conversa.")).toBeVisible();
    useStore();
    await user.click(screen.getByRole("button", { name: "Tentar de novo" }));

    expect(await screen.findByText(/Confira os lançamentos/)).toBeVisible();
  });

  it("test_chat_unknown_conversation_is_not_found", async () => {
    useStore();
    await openChat(`${CHAT}/00000000-0000-4000-8000-00000000dead`);

    expect(await screen.findByRole("heading", { name: "Conversa não encontrada" })).toBeVisible();
  });

  it("test_chat_lists_untitled_conversations_and_loads_more", async () => {
    const many = Array.from({ length: 51 }, (_, n) =>
      makeConversation({
        id: `00000000-0000-4000-8000-${String(100 + n).padStart(12, "0")}`,
        title: n === 0 ? null : `Conversa ${String(n)}`,
      }),
    );
    useStore({ conversations: many });
    const { user } = await openChat();

    expect(await screen.findByRole("link", { name: "Conversa sem título" })).toBeVisible();
    expect(screen.queryByRole("link", { name: "Conversa 50" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Carregar mais" }));

    expect(await screen.findByRole("link", { name: "Conversa 50" })).toBeVisible();
  });

  it("test_chat_empty_list_says_so", async () => {
    useStore({ conversations: [] });
    await openChat();

    expect(await screen.findByText("Você ainda não tem conversas.")).toBeVisible();
  });

  it("test_chat_follows_the_end_only_when_reader_is_there", async () => {
    const source = controlledStream();
    useStore({ reply: () => ({ body: source.stream }) });
    const { user } = await openChat(`${CHAT}/${CONVERSATION_ID}`);
    await screen.findByText(/Confira os lançamentos/);
    const thread = screen.getByRole("list", { name: "Mensagens da conversa" });
    const box = thread.parentElement;
    if (box === null) {
      throw new Error("The thread has no scroll box");
    }
    Object.defineProperty(box, "scrollHeight", { configurable: true, value: 2000 });
    Object.defineProperty(box, "clientHeight", { configurable: true, value: 500 });

    await user.type(composer(), "Outra{Enter}");
    await waitFor(() => {
      expect(box.scrollTop).toBe(2000);
    });
    box.scrollTop = 100;
    act(() => {
      box.dispatchEvent(new Event("scroll"));
    });
    act(() => {
      source.push(
        answerFrames({ ...exchangeIds(1), deltas: ["Mais texto"] })
          .slice(0, 2)
          .join(""),
      );
    });
    await screen.findByText("Mais texto");

    expect(box.scrollTop).toBe(100);
  });
});
