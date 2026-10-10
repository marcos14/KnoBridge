import { waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import {
  CONVERSATION_ID,
  makeWorkspaceConversationDetail,
  makeWorkspaceMessage,
  messageId,
  WORKSPACE_ID,
} from "@/test/factories";
import { workspaceConversationsRecorder } from "@/test/handlers";
import { renderQueryHook } from "@/test/renderWithProviders";
import { server } from "@/test/server";

import { useWorkspaceConversation, useWorkspaceConversations } from "./workspaceConversations";

const DETAIL_PATH = "*/v1/workspaces/:workspaceId/admin/conversations/:conversationId";

/** A detail whose messages arrive `perPage` at a time, out of `total` (the API's paging). */
function pagedDetail(total: number, perPage: number, served = total) {
  const messages = Array.from({ length: served }, (_, n) =>
    makeWorkspaceMessage({ id: messageId(n + 1), content: `Mensagem ${String(n + 1)}` }),
  );
  const offsets: number[] = [];
  server.use(
    http.get(DETAIL_PATH, ({ request }) => {
      const offset = Number(new URL(request.url).searchParams.get("offset"));
      offsets.push(offset);
      const detail = makeWorkspaceConversationDetail(undefined, []);
      return HttpResponse.json({
        ...detail,
        messages: {
          items: messages.slice(offset, offset + perPage),
          total,
          limit: perPage,
          offset,
        },
      });
    }),
  );
  return offsets;
}

describe("useWorkspaceConversation", () => {
  it("test_use_workspace_conversation_joins_every_page_of_messages", async () => {
    const offsets = pagedDetail(5, 2);
    const { result } = renderQueryHook(() =>
      useWorkspaceConversation(WORKSPACE_ID, CONVERSATION_ID),
    );

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(result.current.data?.messages.items.map((message) => message.content)).toEqual([
      "Mensagem 1",
      "Mensagem 2",
      "Mensagem 3",
      "Mensagem 4",
      "Mensagem 5",
    ]);
    expect(offsets).toEqual([0, 2, 4]);
  });

  it("test_use_workspace_conversation_stops_when_a_page_comes_empty", async () => {
    // Messages removed between two pages: the total promised more than there is.
    const offsets = pagedDetail(4, 2, 2);
    const { result } = renderQueryHook(() =>
      useWorkspaceConversation(WORKSPACE_ID, CONVERSATION_ID),
    );

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(result.current.data?.messages.items).toHaveLength(2);
    expect(offsets).toEqual([0, 2]);
  });
});

describe("useWorkspaceConversations", () => {
  it("test_use_workspace_conversations_leaves_out_default_negative_filter", async () => {
    const recorder = workspaceConversationsRecorder();
    server.use(...recorder.handlers);
    const { result } = renderQueryHook(() =>
      useWorkspaceConversations(WORKSPACE_ID, { negativeFeedback: false, limit: 20, offset: 0 }),
    );

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(Object.fromEntries(recorder.listQueries.at(-1) ?? [])).toEqual({
      limit: "20",
      offset: "0",
    });
  });
});
