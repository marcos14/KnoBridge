import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { delay, http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import type { Role } from "@/lib/api/auth";
import {
  CONVERSATION_ID,
  makeMe,
  makeMessage,
  makeQuestion,
  makeThread,
  makeWorkspace,
  messageId,
  WORKSPACE_ID,
} from "@/test/factories";
import {
  answerFrames,
  chatStore,
  controlledStream,
  exchangeIds,
  meAs,
  savedAnswer,
} from "@/test/handlers";
import { renderWithProviders } from "@/test/renderWithProviders";
import { server } from "@/test/server";

const CHAT = `/w/${WORKSPACE_ID}/chat`;

const SEARCH = { status: "ok" as const, sources: 4, new_sources: 2, duration_ms: 80 };

function asRole(role: Role) {
  server.use(meAs(makeMe({ workspaces: [makeWorkspace({ role })] })));
}

async function openConversation(options: Parameters<typeof chatStore>[0] = {}) {
  const store = chatStore({ messages: { [CONVERSATION_ID]: makeThread() }, ...options });
  server.use(...store.handlers);
  const user = userEvent.setup();
  renderWithProviders({ path: `${CHAT}/${CONVERSATION_ID}` });
  await screen.findByRole("list", { name: "Mensagens da conversa" });
  return { user, store };
}

describe("Chat searches in steps", () => {
  it.each<Role>(["owner", "viewer"])(
    "test_chat_shows_the_search_in_progress_and_the_total_for_%s",
    async (role) => {
      asRole(role);
      const source = controlledStream();
      const { user } = await openConversation({
        reply: () => ({
          body: source.stream,
          saved: savedAnswer("completed", "Feche pelo menu Caixa [1].", {
            steps: 3,
            retrieval: {
              version: 1,
              tools: "used",
              reranked: false,
              searches: [
                { ...SEARCH, step: 1, query: null },
                { ...SEARCH, step: 2, query: "tabela do caixa" },
                { ...SEARCH, step: 3, query: "fechamento diário" },
              ],
            },
          }),
        }),
      });

      await user.type(
        screen.getByRole("textbox", { name: "Sua pergunta" }),
        "Como fecho o caixa?{Enter}",
      );
      const [first, second, citations, delta, done] = answerFrames({
        ...exchangeIds(1),
        searches: ["tabela do caixa", "fechamento diário"],
        deltas: ["Feche pelo menu Caixa."],
      });
      act(() => {
        source.push(first ?? "");
      });
      expect(await screen.findByText("Buscando: tabela do caixa")).toBeVisible();
      act(() => {
        source.push(second ?? "");
      });
      expect(await screen.findByText("Buscando: fechamento diário")).toBeVisible();
      expect(screen.queryByText("Buscando: tabela do caixa")).not.toBeInTheDocument();
      act(() => {
        source.push(`${citations ?? ""}${delta ?? ""}`);
      });
      expect(await screen.findByText("Feche pelo menu Caixa.")).toBeVisible();
      expect(screen.queryByText("Buscando: fechamento diário")).not.toBeInTheDocument();
      act(() => {
        source.push(done ?? "");
        source.close();
      });

      const total = await screen.findByText("3 buscas");
      await waitFor(() => {
        expect(total.closest("[aria-live='polite']")).toBeNull();
      });
      await user.click(total);
      const queries = screen.getByRole("list", { name: "Buscas feitas para esta resposta" });
      expect(
        within(queries)
          .getAllByRole("listitem")
          .map((item) => item.textContent),
      ).toEqual(["A pergunta", "tabela do caixa", "fechamento diário"]);
    },
  );

  it("test_chat_shows_the_total_of_done_while_the_conversation_reloads", async () => {
    const source = controlledStream();
    const { user } = await openConversation({ reply: () => ({ body: source.stream }) });
    await user.type(screen.getByRole("textbox", { name: "Sua pergunta" }), "Outra?{Enter}");
    // The reload after `done` never answers: the finished answer stays the streamed one.
    server.use(
      http.get(`*/v1/workspaces/:workspaceId/conversations/:conversationId`, async () => {
        await delay("infinite");
        return HttpResponse.json(null);
      }),
    );

    act(() => {
      source.push(
        answerFrames({ ...exchangeIds(1), searches: ["outra consulta"], deltas: ["Ok."] }).join(""),
      );
      source.close();
    });

    const total = await screen.findByText("2 buscas");
    expect(total.closest("[aria-live='polite']")).not.toBeNull();
  });

  it("test_chat_history_shows_the_searches_of_each_answer", async () => {
    await openConversation({
      messages: {
        [CONVERSATION_ID]: [
          makeQuestion("Primeira", messageId(1)),
          makeMessage({ id: messageId(2), content: "Uma busca só.", steps: 1, retrieval: null }),
          makeQuestion("Segunda", messageId(3)),
          makeMessage({ id: messageId(4), content: "Resposta antiga." }),
        ],
      },
    });

    expect(await screen.findByText("1 busca")).toBeVisible();
    expect(screen.getAllByText(/^\d+ buscas?$/)).toHaveLength(1);
  });
});
