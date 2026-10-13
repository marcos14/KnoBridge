import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { Role } from "@/lib/api/auth";
import { formatDate } from "@/lib/intl";
import {
  ASSISTANT_ID,
  CONVERSATION_ID,
  makeConversationStats,
  makeMe,
  makeWorkspace,
  makeWorkspaceConversation,
  makeWorkspaceConversations,
  memberId,
  WORKSPACE_ID,
} from "@/test/factories";
import {
  conversationStatsServerError,
  meAs,
  workspaceConversationsAs,
  workspaceConversationsRecorder,
  workspaceConversationsServerError,
} from "@/test/handlers";
import { renderWithProviders } from "@/test/renderWithProviders";
import { server } from "@/test/server";

const PATH = `/w/${WORKSPACE_ID}/conversations`;
const TABLE = "Conversas do workspace";
const API_KEY_ID = "00000000-0000-4000-8000-0000000000a1";

function asRole(role: Role) {
  server.use(meAs(makeMe({ workspaces: [makeWorkspace({ role })] })));
}

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

function bodyRows(): HTMLElement[] {
  return within(screen.getByRole("table", { name: TABLE }))
    .getAllByRole("row")
    .slice(1);
}

function rowAt(index: number): HTMLElement {
  const row = bodyRows().at(index);
  if (row === undefined) {
    throw new Error(`No row ${String(index)}`);
  }
  return row;
}

async function pick(user: ReturnType<typeof userEvent.setup>, label: string, option: string) {
  await user.click(screen.getByRole("combobox", { name: label }));
  await user.click(await screen.findByRole("option", { name: option }));
}

describe("ConversationsPage list", () => {
  it("test_conversations_shows_period_totals", async () => {
    record();
    await renderConversations();

    const totals = await screen.findByRole("region", { name: "Totais do período" });
    const start = formatDate(new Date("2026-09-10T12:00:00Z"), "pt-BR");
    const end = formatDate(new Date("2026-10-10T11:59:59.999Z"), "pt-BR");
    expect(within(totals).getByText(`De ${start} a ${end}`)).toBeVisible();
    const pairs = within(totals)
      .getAllByRole("term")
      .map((term) => [term.textContent, term.nextElementSibling?.textContent]);
    expect(pairs).toEqual([
      ["Conversas", "12"],
      ["Mensagens", "48"],
      ["Avaliações 👍", "9"],
      ["Avaliações 👎", "3"],
      ["Respostas sem fonte", "2"],
      ["Respostas com falha", "1"],
      ["Respostas interrompidas", "4"],
    ]);
  });

  it("test_conversations_lists_every_member_conversation", async () => {
    record();
    await renderConversations();

    expect(screen.getByRole("heading", { level: 1, name: "Conversas" })).toBeVisible();
    expect(bodyRows()).toHaveLength(2);
    const first = rowAt(0);
    expect(within(first).getByRole("link", { name: "Como fecho o caixa?" })).toHaveAttribute(
      "href",
      `${PATH}/${CONVERSATION_ID}`,
    );
    expect(within(first).getByText("Ana Teste")).toBeVisible();
    expect(within(first).getByText("ana@example.test")).toBeVisible();
    expect(within(first).getByText("Suporte ERP")).toBeVisible();
    expect(within(first).getByText("4")).toBeVisible();
    expect(within(first).getByLabelText("1 positivas, 1 negativas")).toHaveTextContent(
      "1 👍 · 1 👎",
    );
    expect(within(rowAt(1)).getByRole("link", { name: "Conversa sem título" })).toBeVisible();
    expect(within(rowAt(1)).getByText("Sem mensagens")).toBeVisible();
  });

  it("test_conversations_shows_the_key_of_an_api_conversation", async () => {
    record([
      makeWorkspaceConversation({
        channel: "api",
        user_id: null,
        user_name: null,
        user_email: null,
        api_key_id: API_KEY_ID,
        api_key_name: "Integração ERP",
      }),
    ]);
    await renderConversations();

    const row = rowAt(0);
    expect(within(row).getByText("API · Integração ERP")).toBeVisible();
    expect(within(row).getByText("Chave de API")).toBeVisible();
    expect(within(row).getByRole("link", { name: "Como fecho o caixa?" })).toHaveAttribute(
      "href",
      `${PATH}/${CONVERSATION_ID}`,
    );
  });

  it("test_conversations_channel_filter_goes_to_the_url_and_the_api", async () => {
    const recorder = record();
    const { user, router } = await renderConversations();

    await pick(user, "Canal", "API");

    await waitFor(() => {
      expect(last(recorder.listQueries)).toEqual({ channel: "api", limit: "20", offset: "0" });
    });
    expect(router.state.location.search).toBe("?channel=api");
    await pick(user, "Canal", "Painel");
    await waitFor(() => {
      expect(last(recorder.listQueries)).toMatchObject({ channel: "panel" });
    });
    await pick(user, "Canal", "Todos os canais");

    expect(router.state.location.search).toBe("");
    expect(screen.getByRole("combobox", { name: "Canal" })).toHaveTextContent("Todos os canais");
  });

  it("test_conversations_shared_link_with_a_channel", async () => {
    const recorder = record();
    await renderConversations(`${PATH}?channel=api`);

    expect(last(recorder.listQueries)).toEqual({ channel: "api", limit: "20", offset: "0" });
    expect(screen.getByRole("combobox", { name: "Canal" })).toHaveTextContent("API");
    expect(last(recorder.statsQueries)).toEqual({});
  });

  it("test_conversations_first_requests_have_no_filters", async () => {
    const recorder = record();
    await renderConversations();

    expect(last(recorder.listQueries)).toEqual({ limit: "20", offset: "0" });
    expect(last(recorder.statsQueries)).toEqual({});
    expect(screen.queryByRole("button", { name: "Limpar filtros" })).not.toBeInTheDocument();
  });

  it("test_conversations_filters_go_to_the_url_and_the_api", async () => {
    const recorder = record();
    const { user, router } = await renderConversations();

    await pick(user, "Assistente", "Suporte ERP");
    await pick(user, "Usuário", "Bruno Lima");
    fireEvent.change(screen.getByLabelText("De"), { target: { value: "2026-10-01" } });
    fireEvent.change(screen.getByLabelText("Até"), { target: { value: "2026-10-31" } });
    await user.click(screen.getByRole("checkbox", { name: "Só com 👎" }));

    await waitFor(() => {
      expect(last(recorder.listQueries)).toEqual({
        product_id: ASSISTANT_ID,
        user_id: memberId(1),
        created_from: new Date(2026, 9, 1).toISOString(),
        created_to: new Date(2026, 10, 1).toISOString(),
        negative_feedback: "true",
        limit: "20",
        offset: "0",
      });
    });
    expect(last(recorder.statsQueries)).toEqual({
      created_from: new Date(2026, 9, 1).toISOString(),
      created_to: new Date(2026, 10, 1).toISOString(),
    });
    expect(Object.fromEntries(new URLSearchParams(router.state.location.search))).toEqual({
      assistant: ASSISTANT_ID,
      user: memberId(1),
      from: "2026-10-01",
      to: "2026-10-31",
      negative: "1",
    });
  });

  it("test_conversations_shared_link_opens_the_same_view_and_clears", async () => {
    const stranger = "00000000-0000-4000-8000-00000000beef";
    const recorder = record();
    const { user, router } = await renderConversations(
      `${PATH}?user=${stranger}&negative=1&offset=20`,
    );

    expect(last(recorder.listQueries)).toEqual({
      user_id: stranger,
      negative_feedback: "true",
      limit: "20",
      offset: "20",
    });
    expect(screen.getByRole("combobox", { name: "Usuário" })).toHaveTextContent(
      `Usuário ${stranger}`,
    );
    expect(screen.getByRole("checkbox", { name: "Só com 👎" })).toBeChecked();

    await user.click(screen.getByRole("button", { name: "Limpar filtros" }));

    await waitFor(() => {
      expect(router.state.location.search).toBe("");
    });
    expect(last(recorder.listQueries)).toEqual({ limit: "20", offset: "0" });
  });

  it("test_conversations_clearing_one_filter_keeps_the_others", async () => {
    const recorder = record();
    const { user, router } = await renderConversations(
      `${PATH}?assistant=${ASSISTANT_ID}&from=2026-10-01&negative=1`,
    );

    await pick(user, "Assistente", "Todos os assistentes");
    await user.click(screen.getByRole("checkbox", { name: "Só com 👎" }));
    fireEvent.change(screen.getByLabelText("De"), { target: { value: "" } });
    expect(router.state.location.search).toBe("");
    await waitFor(() => {
      expect(last(recorder.listQueries)).toEqual({ limit: "20", offset: "0" });
    });
    await pick(user, "Usuário", "Bruno Lima");
    await waitFor(() => {
      expect(last(recorder.listQueries)).toMatchObject({ user_id: memberId(1) });
    });
    await pick(user, "Usuário", "Todos os usuários");

    expect(router.state.location.search).toBe("");
  });

  it("test_conversations_pages_through_the_api", async () => {
    const many = Array.from({ length: 25 }, (_, n) =>
      makeWorkspaceConversation({
        id: `00000000-0000-4000-8000-${String(300 + n).padStart(12, "0")}`,
        title: `Conversa ${String(n + 1)}`,
      }),
    );
    const recorder = record(many);
    const { user, router } = await renderConversations();

    expect(screen.getByText("1–20 de 25")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Próxima" }));

    expect(await screen.findByRole("link", { name: "Conversa 21" })).toBeVisible();
    expect(router.state.location.search).toBe("?offset=20");
    expect(last(recorder.listQueries)).toEqual({ limit: "20", offset: "20" });
  });

  it("test_conversations_empty_states", async () => {
    server.use(workspaceConversationsAs([]));
    const { user } = await renderConversations();

    expect(screen.getByText("Nenhuma conversa ainda.")).toBeVisible();
    await user.click(screen.getByRole("checkbox", { name: "Só com 👎" }));

    expect(await screen.findByText("Nenhuma conversa corresponde aos filtros.")).toBeVisible();
  });

  it("test_conversations_load_failures_offer_retry", async () => {
    server.use(workspaceConversationsServerError, conversationStatsServerError);
    const user = userEvent.setup();
    renderWithProviders({ path: PATH });

    expect(await screen.findByText("Não foi possível carregar as conversas.")).toBeVisible();
    expect(await screen.findByText("Não foi possível carregar os totais.")).toBeVisible();
    record(makeWorkspaceConversations(), makeConversationStats({ conversations: 7 }));
    for (const button of screen.getAllByRole("button", { name: "Tentar novamente" })) {
      await user.click(button);
    }

    expect(await screen.findByRole("table", { name: TABLE })).toBeVisible();
    expect(await screen.findByRole("region", { name: "Totais do período" })).toHaveTextContent("7");
  });
});

describe("ConversationsPage access", () => {
  it.each(["owner", "admin"] as const)("test_conversations_%s_sees_the_menu_item", async (role) => {
    asRole(role);
    record();
    await renderConversations();

    const nav = screen.getByRole("navigation", { name: "Navegação principal" });
    expect(within(nav).getByRole("link", { name: "Conversas" })).toHaveAttribute("href", PATH);
  });

  it.each(["editor", "viewer"] as const)(
    "test_conversations_%s_has_no_menu_item_and_gets_403",
    async (role) => {
      asRole(role);
      const recorder = record();
      renderWithProviders({ path: PATH });

      expect(await screen.findByRole("heading", { level: 1, name: "Acesso negado" })).toBeVisible();
      const nav = screen.getByRole("navigation", { name: "Navegação principal" });
      expect(within(nav).queryByRole("link", { name: "Conversas" })).not.toBeInTheDocument();
      expect(recorder.listQueries).toHaveLength(0);
    },
  );

  it("test_conversations_detail_route_is_closed_to_editors", async () => {
    asRole("editor");
    renderWithProviders({ path: `${PATH}/${CONVERSATION_ID}` });

    expect(await screen.findByRole("heading", { level: 1, name: "Acesso negado" })).toBeVisible();
  });
});
