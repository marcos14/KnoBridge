import { act, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import {
  CONVERSATION_ID,
  makeConversation,
  makeConversationDetail,
  makeMessage,
  messageId,
  WORKSPACE_ID,
} from "@/test/factories";
import { chatStore, conversationsAs } from "@/test/handlers";
import { renderQueryHook } from "@/test/renderWithProviders";
import { server } from "@/test/server";

import {
  conversationQueryKey,
  type ConversationDetail,
  useConversation,
  useConversations,
  useCreateConversation,
  useDeleteConversation,
  useSetFeedback,
} from "./conversations";

const CONVERSATION_PATH = "*/v1/workspaces/:workspaceId/conversations/:conversationId";

function conversationNumber(n: number) {
  return makeConversation({
    id: `00000000-0000-4000-8000-${String(n).padStart(12, "0")}`,
    title: `Conversa ${String(n)}`,
  });
}

describe("useConversations", () => {
  it("test_use_conversations_loads_more_pages_on_demand", async () => {
    server.use(conversationsAs(Array.from({ length: 60 }, (_, n) => conversationNumber(n))));
    const { result } = renderQueryHook(() => useConversations(WORKSPACE_ID));

    await waitFor(() => {
      expect(result.current.conversations).toHaveLength(50);
    });
    expect(result.current.hasNextPage).toBe(true);

    await act(async () => {
      await result.current.fetchNextPage();
    });

    await waitFor(() => {
      expect(result.current.conversations).toHaveLength(60);
    });
    expect(result.current.hasNextPage).toBe(false);
  });

  it("test_use_conversations_skips_repeated_conversations", async () => {
    const first = conversationNumber(1);
    server.use(
      http.get("*/v1/workspaces/:workspaceId/conversations", ({ request }) => {
        const offset = Number(new URL(request.url).searchParams.get("offset"));
        return HttpResponse.json(
          offset === 0
            ? { items: [first], total: 3, limit: 50, offset }
            : { items: [first, conversationNumber(2)], total: 3, limit: 50, offset },
        );
      }),
    );
    const { result } = renderQueryHook(() => useConversations(WORKSPACE_ID));
    await waitFor(() => {
      expect(result.current.hasNextPage).toBe(true);
    });

    await act(async () => {
      await result.current.fetchNextPage();
    });

    await waitFor(() => {
      expect(result.current.conversations.map((item) => item.title)).toEqual([
        "Conversa 1",
        "Conversa 2",
      ]);
    });
    // Offsets count rows read (1 + 2 of 3), not distinct conversations.
    expect(result.current.hasNextPage).toBe(false);
  });

  it("test_use_conversations_empty_page_ends_the_list", async () => {
    server.use(
      http.get("*/v1/workspaces/:workspaceId/conversations", () =>
        HttpResponse.json({ items: [], total: 5, limit: 50, offset: 0 }),
      ),
    );
    const { result } = renderQueryHook(() => useConversations(WORKSPACE_ID));

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(result.current.hasNextPage).toBe(false);
  });
});

describe("useConversation", () => {
  it("test_use_conversation_joins_message_pages", async () => {
    const messages = Array.from({ length: 501 }, (_, n) => makeMessage({ id: messageId(n) }));
    const offsets: string[] = [];
    server.use(
      http.get(CONVERSATION_PATH, ({ request }) => {
        const query = new URL(request.url).searchParams;
        const offset = Number(query.get("offset"));
        offsets.push(String(offset));
        const detail = makeConversationDetail(
          makeConversation(),
          messages.slice(offset, offset + 500),
        );
        return HttpResponse.json({
          ...detail,
          messages: { ...detail.messages, total: 501, offset },
        });
      }),
    );
    const { result } = renderQueryHook(() => useConversation(WORKSPACE_ID, CONVERSATION_ID));

    await waitFor(() => {
      expect(result.current.data?.messages.items).toHaveLength(501);
    });
    expect(offsets).toEqual(["0", "500"]);
  });

  it("test_use_conversation_stops_on_empty_message_page", async () => {
    server.use(
      http.get(CONVERSATION_PATH, ({ request }) => {
        const offset = Number(new URL(request.url).searchParams.get("offset"));
        const detail = makeConversationDetail(
          makeConversation(),
          offset === 0 ? [makeMessage()] : [],
        );
        return HttpResponse.json({ ...detail, messages: { ...detail.messages, total: 4 } });
      }),
    );
    const { result } = renderQueryHook(() => useConversation(WORKSPACE_ID, CONVERSATION_ID));

    await waitFor(() => {
      expect(result.current.data?.messages.items).toHaveLength(1);
    });
  });
});

describe("conversation mutations", () => {
  it("test_use_create_conversation_posts_the_assistant", async () => {
    const store = chatStore();
    server.use(...store.handlers);
    const { result } = renderQueryHook(() => useCreateConversation(WORKSPACE_ID));

    await act(async () => {
      await result.current.mutateAsync("assistant-1");
    });

    expect(store.created).toEqual(["assistant-1"]);
  });

  it("test_use_delete_conversation_drops_the_cached_detail", async () => {
    const store = chatStore();
    server.use(...store.handlers);
    const { result, queryClient } = renderQueryHook(() => useDeleteConversation(WORKSPACE_ID));
    queryClient.setQueryData(conversationQueryKey(WORKSPACE_ID, CONVERSATION_ID), {});

    await act(async () => {
      await result.current.mutateAsync(CONVERSATION_ID);
    });

    expect(store.deleted).toEqual([CONVERSATION_ID]);
    expect(
      queryClient.getQueryData(conversationQueryKey(WORKSPACE_ID, CONVERSATION_ID)),
    ).toBeUndefined();
  });

  it("test_use_set_feedback_writes_into_the_cached_conversation", async () => {
    const answer = makeMessage();
    const other = makeMessage({ id: messageId(9) });
    const store = chatStore({ messages: { [CONVERSATION_ID]: [answer, other] } });
    server.use(...store.handlers);
    const { result, queryClient } = renderQueryHook(() => useSetFeedback(WORKSPACE_ID));
    const key = conversationQueryKey(WORKSPACE_ID, CONVERSATION_ID);
    queryClient.setQueryData(key, makeConversationDetail(makeConversation(), [answer, other]));

    await act(async () => {
      await result.current.mutateAsync({
        conversationId: CONVERSATION_ID,
        messageId: answer.id,
        feedback: { rating: "down", comment: "Faltou o passo 2." },
      });
    });

    const cached = queryClient.getQueryData<ConversationDetail>(key);
    expect(cached?.messages.items[0]?.feedback).toMatchObject({
      rating: "down",
      comment: "Faltou o passo 2.",
    });
    expect(cached?.messages.items[1]?.feedback).toBeNull();
    expect(store.feedback).toEqual([
      { messageId: answer.id, body: { rating: "down", comment: "Faltou o passo 2." } },
    ]);
  });

  it("test_use_set_feedback_without_cached_conversation_keeps_cache_empty", async () => {
    const { result, queryClient } = renderQueryHook(() => useSetFeedback(WORKSPACE_ID));

    await act(async () => {
      await result.current.mutateAsync({
        conversationId: CONVERSATION_ID,
        messageId: messageId(2),
        feedback: { rating: "up", comment: "" },
      });
    });

    expect(
      queryClient.getQueryData(conversationQueryKey(WORKSPACE_ID, CONVERSATION_ID)),
    ).toBeUndefined();
  });
});
