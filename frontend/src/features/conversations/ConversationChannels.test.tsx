import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import {
  CONVERSATION_ID,
  makeWorkspaceConversation,
  makeWorkspaceConversationDetail,
  makeWorkspaceFeedback,
  makeWorkspaceMessage,
  messageId,
  WORKSPACE_ID,
} from "@/test/factories";
import {
  widgetsAs,
  workspaceConversationAs,
  workspaceConversationsRecorder,
} from "@/test/handlers";
import { renderWithProviders } from "@/test/renderWithProviders";
import { server } from "@/test/server";
import { OTHER_WIDGET_ID, WIDGET_ID } from "@/test/widgetFactories";

const PATH = `/w/${WORKSPACE_ID}/conversations`;
const TABLE = "Conversas do workspace";
const API_KEY_ID = "00000000-0000-4000-8000-0000000000a1";

const MCP_ROW = makeWorkspaceConversation({
  channel: "mcp",
  user_id: null,
  user_name: null,
  user_email: null,
  api_key_id: API_KEY_ID,
  api_key_name: "claude-code",
});

const WIDGET_ROW = makeWorkspaceConversation({
  id: "00000000-0000-4000-8000-0000000000d9",
  channel: "widget",
  level: "end_user",
  user_id: null,
  user_name: null,
  user_email: null,
  widget_id: WIDGET_ID,
  widget_name: "Site público",
  visitor: { name: "Ana Souza", email: "ana@exemplo.com.br", external_id: "cliente-42" },
});

const ANONYMOUS_ROW = makeWorkspaceConversation({
  ...WIDGET_ROW,
  id: "00000000-0000-4000-8000-0000000000da",
  visitor: null,
});

function record(...args: Parameters<typeof workspaceConversationsRecorder>) {
  const recorder = workspaceConversationsRecorder(...args);
  server.use(...recorder.handlers);
  return recorder;
}

function last(queries: URLSearchParams[]): Record<string, string> {
  return Object.fromEntries(queries.at(-1) ?? []);
}

async function renderConversations(path = PATH) {
  const user = userEvent.setup();
  const rendered = renderWithProviders({ path });
  await screen.findByRole("table", { name: TABLE });
  return { user, ...rendered };
}

function rowAt(index: number): HTMLElement {
  const row = within(screen.getByRole("table", { name: TABLE }))
    .getAllByRole("row")
    .at(index + 1);
  if (row === undefined) {
    throw new Error(`No row ${String(index)}`);
  }
  return row;
}

async function pick(user: ReturnType<typeof userEvent.setup>, label: string, option: string) {
  await user.click(screen.getByRole("combobox", { name: label }));
  await user.click(await screen.findByRole("option", { name: option }));
}

describe("Conversations of MCP and widgets", () => {
  it("test_conversations_label_mcp_and_widget_owners", async () => {
    record([MCP_ROW, WIDGET_ROW, ANONYMOUS_ROW]);
    await renderConversations();

    expect(within(rowAt(0)).getByText("MCP · claude-code")).toBeVisible();
    expect(within(rowAt(0)).getByText("Chave de API")).toBeVisible();
    expect(within(rowAt(1)).getByText("Widget · Site público")).toBeVisible();
    expect(within(rowAt(1)).getByText("Visitante: Ana Souza (ana@exemplo.com.br)")).toBeVisible();
    expect(within(rowAt(2)).getByText("Visitante anônimo")).toBeVisible();
  });

  it("test_conversations_channel_filter_offers_mcp_and_widget", async () => {
    const recorder = record();
    const { user, router } = await renderConversations();

    await pick(user, "Canal", "MCP");
    await waitFor(() => {
      expect(last(recorder.listQueries)).toMatchObject({ channel: "mcp" });
    });
    await pick(user, "Canal", "Widget");

    await waitFor(() => {
      expect(last(recorder.listQueries)).toMatchObject({ channel: "widget" });
    });
    expect(router.state.location.search).toBe("?channel=widget");
  });

  it("test_conversations_widget_filter_goes_to_the_url_and_the_api", async () => {
    const recorder = record();
    const { user, router } = await renderConversations();

    await pick(user, "Widget", "Portal interno");

    await waitFor(() => {
      expect(last(recorder.listQueries)).toEqual({
        widget_id: OTHER_WIDGET_ID,
        limit: "20",
        offset: "0",
      });
    });
    expect(router.state.location.search).toBe(`?widget=${OTHER_WIDGET_ID}`);
    await pick(user, "Widget", "Todos os widgets");
    await waitFor(() => {
      expect(router.state.location.search).toBe("");
    });
  });

  it("test_conversations_widget_filter_keeps_a_widget_not_listed", async () => {
    server.use(...widgetsAs([]));
    record();
    await renderConversations(`${PATH}?widget=${WIDGET_ID}`);

    expect(screen.getByRole("combobox", { name: "Widget" })).toHaveTextContent(
      `Widget ${WIDGET_ID}`,
    );
  });

  it("test_conversation_detail_of_a_widget_shows_the_visitor", async () => {
    server.use(
      workspaceConversationAs(
        makeWorkspaceConversationDetail({ ...WIDGET_ROW, id: CONVERSATION_ID }, [
          makeWorkspaceMessage({
            id: messageId(1),
            role: "user",
            content: "Como fecho o caixa?",
            citations: [],
          }),
          makeWorkspaceMessage({
            id: messageId(2),
            feedback: [
              makeWorkspaceFeedback({
                rating: "down",
                comment: "Não ajudou.",
                user_id: null,
                user_name: null,
                user_email: null,
              }),
            ],
          }),
        ]),
      ),
    );
    renderWithProviders({ path: `${PATH}/${CONVERSATION_ID}` });

    expect(
      await screen.findByText(
        "Widget · Site público · Visitante: Ana Souza (ana@exemplo.com.br) em Suporte ERP, nível Usuário final",
      ),
    ).toBeVisible();
    expect(screen.getByText(/Pergunta de Ana Souza/)).toBeVisible();
    expect(screen.getByText("👎 Visitante")).toBeVisible();
  });

  it("test_conversation_detail_of_mcp_shows_the_key", async () => {
    server.use(
      workspaceConversationAs(makeWorkspaceConversationDetail({ ...MCP_ROW, id: CONVERSATION_ID })),
    );
    renderWithProviders({ path: `${PATH}/${CONVERSATION_ID}` });

    expect(
      await screen.findByText("MCP · claude-code em Suporte ERP, nível Desenvolvimento e produto"),
    ).toBeVisible();
  });
});
