import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Message } from "@/lib/api/conversations";
import { TICKET_REQUEST_POLL_INTERVAL_MS } from "@/lib/api/ticketRequests";
import {
  CONVERSATION_ID,
  makeMessage,
  makeQuestion,
  makeThread,
  messageId,
  WORKSPACE_ID,
} from "@/test/factories";
import {
  answerFrames,
  apiErrorResponse,
  chatStore,
  exchangeIds,
  pendingPost,
  savedAnswer,
} from "@/test/handlers";
import { renderWithProviders } from "@/test/renderWithProviders";
import { server } from "@/test/server";
import { makeTicketRequest, makeTicketRequestPreview } from "@/test/ticketFactories";

const PATH = `/w/${WORKSPACE_ID}/chat/${CONVERSATION_ID}`;
const NO_SOURCE = "Não encontrei isso nas fontes.";
const OPEN = "Abrir chamado";
const MENU = "Abrir chamado da conversa";
const PREVIEW =
  "*/v1/workspaces/:workspaceId/conversations/:conversationId/ticket-requests/preview";

/** A question answered without a source (answer `messageId(2)`). */
function noSourceThread(extra: Partial<Message> = {}): Message[] {
  return [
    makeQuestion("Como emito nota fiscal para cliente do exterior?"),
    makeMessage({ content: NO_SOURCE, status: "no_source", model: null, ...extra }),
  ];
}

function useStore(options: Parameters<typeof chatStore>[0] = {}) {
  const store = chatStore({
    messages: { [CONVERSATION_ID]: noSourceThread() },
    ticketRequestsEnabled: true,
    ...options,
  });
  server.use(...store.handlers);
  return store;
}

async function openChat() {
  const user = userEvent.setup(
    vi.isFakeTimers() ? { advanceTimers: vi.advanceTimersByTime.bind(vi) } : {},
  );
  renderWithProviders({ path: PATH });
  await screen.findByText(NO_SOURCE);
  return user;
}

async function openDialog(user: ReturnType<typeof userEvent.setup>, name = OPEN) {
  await user.click(await screen.findByRole("button", { name }));
  return screen.findByRole("dialog", { name: "Abrir chamado" });
}

afterEach(() => {
  vi.useRealTimers();
});

describe("ticket request in the chat", () => {
  it("test_ticket_request_previews_edits_and_confirms", async () => {
    const store = useStore();
    const user = await openChat();

    const dialog = await openDialog(user);

    expect(await within(dialog).findByText(makeTicketRequestPreview().question)).toBeVisible();
    expect(store.ticketPreviews).toEqual([messageId(2)]);
    const summary = within(dialog).getByLabelText("Resumo");
    expect(summary).toHaveValue(makeTicketRequestPreview().summary);
    expect(
      within(dialog).getByText(
        "Escrito pelo assistente a partir da conversa. Revise antes de enviar.",
      ),
    ).toBeVisible();
    expect(within(dialog).getByText("Solicitante: Ana Teste (ana@example.test)")).toBeVisible();
    expect(within(dialog).getByText("2 mensagens da conversa vão junto.")).toBeVisible();
    await user.clear(summary);
    await user.type(summary, "Nota de exportação: falta o passo a passo.");
    await user.click(within(dialog).getByRole("button", { name: "Confirmar e abrir chamado" }));

    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
    expect(store.ticketCreations).toEqual([
      { messageId: messageId(2), summary: "Nota de exportação: falta o passo a passo." },
    ]);
    expect(await screen.findByText("Enviando o chamado…")).toBeVisible();
    expect(screen.queryByRole("button", { name: OPEN })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: MENU })).not.toBeInTheDocument();
  });

  it("test_ticket_request_polls_until_delivered_and_stops", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const store = useStore();
    const user = await openChat();
    const dialog = await openDialog(user);
    await within(dialog).findByLabelText("Resumo");
    await user.click(within(dialog).getByRole("button", { name: "Confirmar e abrir chamado" }));
    await screen.findByText("Enviando o chamado…");

    await act(async () => {
      await vi.advanceTimersByTimeAsync(TICKET_REQUEST_POLL_INTERVAL_MS);
    });
    await waitFor(() => {
      expect(store.ticketReads()).toBe(1);
    });
    expect(screen.getByText("Enviando o chamado…")).toBeVisible();

    store.settleTicket({
      status: "delivered",
      attempts: 1,
      external_ticket_id: "48213",
      external_url: "https://suporte.example.test/chamados/48213",
      delivered_at: "2026-10-12T13:00:05Z",
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(TICKET_REQUEST_POLL_INTERVAL_MS);
    });

    expect(await screen.findByText("Chamado 48213 aberto.")).toBeVisible();
    const link = screen.getByRole("link", { name: "Abrir o chamado" });
    expect(link).toHaveAttribute("href", "https://suporte.example.test/chamados/48213");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
    const reads = store.ticketReads();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(TICKET_REQUEST_POLL_INTERVAL_MS * 3);
    });
    expect(store.ticketReads()).toBe(reads);
  });

  it("test_ticket_request_failed_shows_the_reason", async () => {
    useStore({
      messages: {
        [CONVERSATION_ID]: noSourceThread({
          ticket_request: makeTicketRequest({
            status: "failed",
            attempts: 1,
            error_code: "webhook_rejected",
          }),
        }),
      },
    });
    await openChat();

    expect(
      await screen.findByText("Não foi possível abrir o chamado. O destino recusou o envio."),
    ).toBeVisible();
    expect(screen.queryByRole("button", { name: OPEN })).not.toBeInTheDocument();
  });

  it("test_ticket_request_delivered_without_number_or_safe_link", async () => {
    const store = useStore({
      messages: {
        [CONVERSATION_ID]: noSourceThread({
          ticket_request: makeTicketRequest({
            status: "delivered",
            external_url: "javascript:alert(1)",
            delivered_at: "2026-10-12T13:00:05Z",
          }),
        }),
      },
    });
    await openChat();

    expect(await screen.findByText("Chamado aberto no sistema de chamados.")).toBeVisible();
    expect(screen.queryByRole("link", { name: "Abrir o chamado" })).not.toBeInTheDocument();
    expect(store.ticketReads()).toBe(0);
  });

  it("test_ticket_request_is_not_offered_when_the_assistant_has_no_webhook", async () => {
    useStore({ ticketRequestsEnabled: false });
    await openChat();

    expect(screen.queryByRole("button", { name: OPEN })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: MENU })).not.toBeInTheDocument();
  });

  it("test_ticket_request_after_a_streamed_no_source_answer", async () => {
    const store = useStore({
      messages: { [CONVERSATION_ID]: makeThread() },
      reply: () => ({
        body: answerFrames({
          ...exchangeIds(1),
          deltas: [NO_SOURCE],
          end: { status: "no_source" },
          ticketRequestsEnabled: true,
        }).join(""),
        saved: savedAnswer("no_source", NO_SOURCE, { model: null }),
      }),
    });
    const user = userEvent.setup();
    renderWithProviders({ path: PATH });
    await screen.findByText(/Confira os lançamentos/);
    // A completed answer is offered only by the conversation menu.
    expect(screen.queryByRole("button", { name: OPEN })).not.toBeInTheDocument();
    expect(await screen.findByRole("button", { name: MENU })).toBeVisible();

    await user.type(screen.getByRole("textbox", { name: "Sua pergunta" }), "E a nota?{Enter}");
    await openDialog(user);

    expect(store.ticketPreviews).toEqual([exchangeIds(1).messageId]);
  });

  it("test_ticket_request_from_the_conversation_menu_asks_for_the_last_answer", async () => {
    const store = useStore({ messages: { [CONVERSATION_ID]: makeThread() } });
    const user = userEvent.setup();
    renderWithProviders({ path: PATH });

    const dialog = await openDialog(user, MENU);

    expect(await within(dialog).findByLabelText("Resumo")).toBeVisible();
    expect(store.ticketPreviews).toEqual([messageId(2)]);
  });

  it("test_ticket_request_preview_without_summary_says_it_is_the_question", async () => {
    useStore({
      ticketPreview: (id) =>
        makeTicketRequestPreview({
          message_id: id,
          summary: "Como emito nota fiscal para cliente do exterior?",
          summary_generated: false,
          messages: makeTicketRequestPreview().messages.slice(0, 1),
        }),
    });
    const user = await openChat();
    const dialog = await openDialog(user);

    expect(
      await within(dialog).findByText(
        "Não foi possível gerar o resumo: o texto é a sua pergunta. Revise antes de enviar.",
      ),
    ).toBeVisible();
    expect(within(dialog).getByText("1 mensagem da conversa vai junto.")).toBeVisible();
  });

  it("test_ticket_request_summary_is_required", async () => {
    const store = useStore();
    const user = await openChat();
    const dialog = await openDialog(user);

    await user.clear(await within(dialog).findByLabelText("Resumo"));
    await user.click(within(dialog).getByRole("button", { name: "Confirmar e abrir chamado" }));

    expect(await within(dialog).findByText("Escreva o resumo do pedido.")).toBeVisible();
    expect(store.ticketCreations).toEqual([]);
  });

  it("test_ticket_request_preview_error_is_shown_and_closes", async () => {
    useStore({ ticketPreview: () => apiErrorResponse(409, "ticket_webhook_not_configured") });
    const user = await openChat();
    const dialog = await openDialog(user);

    expect(await within(dialog).findByRole("alert")).toHaveTextContent(
      "O webhook de chamados deste produto não está configurado.",
    );
    await user.click(within(dialog).getByRole("button", { name: "Fechar" }));
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
  });

  it("test_ticket_request_can_be_cancelled_while_preparing", async () => {
    const store = useStore();
    server.use(pendingPost(PREVIEW));
    const user = await openChat();
    const dialog = await openDialog(user);

    expect(within(dialog).getByRole("status")).toHaveTextContent("Preparando o pedido…");
    await user.click(within(dialog).getByRole("button", { name: "Cancelar" }));

    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
    expect(store.ticketCreations).toEqual([]);
  });

  it("test_ticket_request_that_already_exists_reloads_the_conversation", async () => {
    const store = useStore();
    const user = await openChat();
    const dialog = await openDialog(user);
    await within(dialog).findByLabelText("Resumo");
    // Someone (another tab) asked first: the server now has a request for this answer.
    server.use(
      ...chatStore({
        messages: { [CONVERSATION_ID]: noSourceThread({ ticket_request: makeTicketRequest() }) },
        ticketRequestsEnabled: true,
      }).handlers,
    );

    await user.click(within(dialog).getByRole("button", { name: "Confirmar e abrir chamado" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent(
      "Já existe um pedido de chamado para esta resposta.",
    );
    expect(await screen.findByText("Enviando o chamado…")).toBeInTheDocument();
    expect(store.ticketCreations).toEqual([]);
  });
});
