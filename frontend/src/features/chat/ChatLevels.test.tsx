import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import {
  CONVERSATION_ID,
  makeConversation,
  makeProduct,
  makeThread,
  OTHER_CONVERSATION_ID,
  OTHER_PRODUCT_ID,
  PRODUCT_ID,
  WORKSPACE_ID,
} from "@/test/factories";
import {
  apiErrorResponse,
  chatStore,
  conversationsRecorder,
  createConversationFails,
  messagesRespond,
  productsAs,
} from "@/test/handlers";
import { renderWithProviders } from "@/test/renderWithProviders";
import { server } from "@/test/server";

const CHAT = `/w/${WORKSPACE_ID}/chat`;

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

function levelRadio(name: string) {
  return screen.getByRole("radio", { name });
}

describe("Chat with product and level", () => {
  it("test_chat_level_starts_at_the_member_max_and_levels_above_are_unavailable", async () => {
    const store = useStore();
    server.use(productsAs([makeProduct({ my_max_level: "support" })]));
    const { user } = await openChat();
    await screen.findByRole("radiogroup", { name: "Nível de resposta" });

    expect(levelRadio("Suporte")).toBeChecked();
    expect(levelRadio("Usuário final")).toBeEnabled();
    const above = levelRadio("Desenvolvimento e produto");
    expect(above).toBeDisabled();
    expect(above).toHaveAccessibleDescription(
      "Indisponível: o seu nível máximo neste produto é Suporte.",
    );
    expect(levelRadio("Usuário final")).toHaveAccessibleDescription(/^Quem usa o sistema/);

    await user.click(levelRadio("Usuário final"));
    await user.type(composer(), "Como fecho o caixa?{Enter}");

    await waitFor(() => {
      expect(store.created).toEqual([{ product_id: PRODUCT_ID, level: "end_user" }]);
    });
  });

  it("test_chat_level_goes_back_to_the_max_of_the_chosen_product", async () => {
    const store = useStore();
    server.use(
      productsAs([
        makeProduct({ my_max_level: "product_dev" }),
        makeProduct({ id: OTHER_PRODUCT_ID, name: "Fiscal", my_max_level: "end_user" }),
      ]),
    );
    const { user } = await openChat();
    await screen.findByRole("radiogroup", { name: "Nível de resposta" });
    await user.click(levelRadio("Suporte"));

    await user.click(screen.getByRole("combobox", { name: "Produto" }));
    await user.click(await screen.findByRole("option", { name: "Fiscal" }));

    expect(levelRadio("Usuário final")).toBeChecked();
    expect(levelRadio("Suporte")).toBeDisabled();
    await user.type(composer(), "Nota?{Enter}");
    await waitFor(() => {
      expect(store.created).toEqual([{ product_id: OTHER_PRODUCT_ID, level: "end_user" }]);
    });
  });

  it("test_chat_level_not_configured_asks_for_an_admin", async () => {
    useStore();
    server.use(createConversationFails(409, "level_not_configured", { level: "support" }));
    const { user } = await openChat();
    await screen.findByRole("radiogroup", { name: "Nível de resposta" });

    await user.type(composer(), "Pergunta{Enter}");

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "O nível Suporte ainda não foi configurado neste workspace: peça a um admin",
    );
    expect(composer()).toHaveValue("Pergunta");
  });

  it("test_chat_question_above_the_max_names_both_levels", async () => {
    useStore();
    server.use(
      messagesRespond(() =>
        apiErrorResponse(403, "level_not_allowed", {
          requested_level: "product_dev",
          max_level: "end_user",
          reason: "member",
        }),
      ),
    );
    const { user } = await openChat(`${CHAT}/${CONVERSATION_ID}`);
    await screen.findByText(/Confira os lançamentos/);

    await user.type(composer(), "Posso?{Enter}");

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "O seu nível máximo neste produto é Usuário final e esta conversa está no nível Desenvolvimento e produto. Abra uma nova conversa num nível permitido.",
    );
  });

  it("test_chat_question_to_an_inactive_product_says_so", async () => {
    useStore();
    server.use(messagesRespond(() => apiErrorResponse(409, "product_inactive")));
    const { user } = await openChat(`${CHAT}/${CONVERSATION_ID}`);
    await screen.findByText(/Confira os lançamentos/);

    await user.type(composer(), "Ainda?{Enter}");

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Este produto foi desativado e não aceita novas conversas nem perguntas.",
    );
  });

  it("test_chat_conversation_shows_its_product_and_level_seal", async () => {
    useStore({ conversations: [makeConversation({ level: "support" })] });
    await openChat(`${CHAT}/${CONVERSATION_ID}`);

    expect(await screen.findByText("Produto: Suporte ERP")).toBeVisible();
    expect(screen.getByText("Nível: Suporte")).toBeVisible();
    const list = screen.getByRole("navigation", { name: "Suas conversas" });
    expect(
      within(list).getByRole("link", { name: "Como fecho o caixa? Suporte ERP · Suporte" }),
    ).toBeVisible();
    expect(screen.queryByText(/não aceita novas perguntas/)).not.toBeInTheDocument();
  });

  it("test_chat_conversation_above_the_current_max_warns_before_asking", async () => {
    useStore();
    server.use(productsAs([makeProduct({ my_max_level: "end_user" })]));
    await openChat(`${CHAT}/${CONVERSATION_ID}`);

    expect(
      await screen.findByText(
        "O seu nível máximo neste produto agora é Usuário final: esta conversa, no nível Desenvolvimento e produto, não aceita novas perguntas. Abra uma nova conversa.",
      ),
    ).toBeVisible();
  });

  it("test_chat_list_filters_by_product_and_level", async () => {
    useStore();
    const recorder = conversationsRecorder([
      makeConversation(),
      makeConversation({ id: OTHER_CONVERSATION_ID, title: "Nota", level: "end_user" }),
    ]);
    server.use(recorder.handler);
    const { user } = await openChat();
    const list = screen.getByRole("navigation", { name: "Suas conversas" });
    await within(list).findByRole("link", { name: /^Nota / });

    await user.click(within(list).getByRole("combobox", { name: "Nível das conversas" }));
    await user.click(await screen.findByRole("option", { name: "Usuário final" }));
    await waitFor(() => {
      expect(within(list).queryByRole("link", { name: /^Como fecho/ })).not.toBeInTheDocument();
    });
    expect(within(list).getByRole("link", { name: /^Nota / })).toBeVisible();
    await user.click(within(list).getByRole("combobox", { name: "Produto das conversas" }));
    await user.click(await screen.findByRole("option", { name: "Suporte ERP" }));

    await waitFor(() => {
      expect(recorder.queries.at(-1)).toBe(
        `?product_id=${PRODUCT_ID}&level=end_user&limit=50&offset=0`,
      );
    });
    await user.click(within(list).getByRole("combobox", { name: "Nível das conversas" }));
    await user.click(await screen.findByRole("option", { name: "Suporte" }));
    expect(await within(list).findByText("Nenhuma conversa com estes filtros.")).toBeVisible();
    await user.click(within(list).getByRole("combobox", { name: "Produto das conversas" }));
    await user.click(await screen.findByRole("option", { name: "Todos os produtos" }));
    await user.click(within(list).getByRole("combobox", { name: "Nível das conversas" }));
    await user.click(await screen.findByRole("option", { name: "Todos os níveis" }));
    expect(await within(list).findByRole("link", { name: /^Como fecho/ })).toBeVisible();
  });
});
