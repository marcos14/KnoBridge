import {
  type QueryClient,
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import { apiClient, unwrap } from "./client";
import type { components } from "./schema.gen";

export type Conversation = components["schemas"]["ConversationOut"];
export type ConversationDetail = components["schemas"]["ConversationDetail"];
export type ConversationPage = components["schemas"]["ConversationPage"];
export type Message = components["schemas"]["MessageOut"];
export type MessageStatus = components["schemas"]["MessageStatus"];
export type Citation = components["schemas"]["CitationOut"];
export type Feedback = components["schemas"]["FeedbackOut"];
export type FeedbackInput = components["schemas"]["FeedbackIn"];

/** Conversations per page of the chat sidebar ("load more" asks for the next one). */
export const CONVERSATIONS_PAGE_SIZE = 50;
/** Largest page of messages `GET .../conversations/{id}` accepts. */
export const MESSAGES_PAGE_SIZE = 500;

export function conversationsQueryKey(workspaceId: string) {
  return ["api", "workspaces", workspaceId, "conversations"] as const;
}

export function conversationQueryKey(workspaceId: string, conversationId: string) {
  return [...conversationsQueryKey(workspaceId), conversationId] as const;
}

/** The pages of the list query, so the detail key (a longer prefix) is not caught by it. */
function conversationListQueryKey(workspaceId: string) {
  return [...conversationsQueryKey(workspaceId), "list"] as const;
}

/**
 * The caller's own conversations, most recently active first, `CONVERSATIONS_PAGE_SIZE` at a
 * time. `conversations` flattens the loaded pages without repeats (a conversation that moves to
 * the top between two pages would otherwise show twice).
 */
export function useConversations(workspaceId: string) {
  const query = useInfiniteQuery({
    queryKey: conversationListQueryKey(workspaceId),
    initialPageParam: 0,
    queryFn: async ({ pageParam, signal }) =>
      unwrap(
        await apiClient.GET("/v1/workspaces/{workspace_id}/conversations", {
          params: {
            path: { workspace_id: workspaceId },
            query: { limit: CONVERSATIONS_PAGE_SIZE, offset: pageParam },
          },
          signal,
        }),
      ),
    getNextPageParam: (last: ConversationPage) => {
      const next = last.offset + last.items.length;
      return last.items.length > 0 && next < last.total ? next : undefined;
    },
  });
  const seen = new Set<string>();
  const conversations = (query.data?.pages ?? [])
    .flatMap((page) => page.items)
    .filter((item) => !seen.has(item.id) && Boolean(seen.add(item.id)));
  return { ...query, conversations };
}

/**
 * A conversation with all its messages in order. The API pages messages; a long conversation is
 * read in pages of `MESSAGES_PAGE_SIZE` and joined.
 */
export function useConversation(workspaceId: string, conversationId: string) {
  return useQuery({
    queryKey: conversationQueryKey(workspaceId, conversationId),
    queryFn: async ({ signal }) => {
      const read = async (offset: number) =>
        unwrap(
          await apiClient.GET("/v1/workspaces/{workspace_id}/conversations/{conversation_id}", {
            params: {
              path: { workspace_id: workspaceId, conversation_id: conversationId },
              query: { limit: MESSAGES_PAGE_SIZE, offset },
            },
            signal,
          }),
        );
      const detail = await read(0);
      const items = [...detail.messages.items];
      while (items.length < detail.messages.total) {
        const next = await read(items.length);
        if (next.messages.items.length === 0) {
          break;
        }
        items.push(...next.messages.items);
      }
      return { ...detail, messages: { ...detail.messages, items } } satisfies ConversationDetail;
    },
  });
}

/** `POST /v1/workspaces/{id}/conversations` (201); 409 `assistant_inactive`. */
export function useCreateConversation(workspaceId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (assistantId: string) =>
      unwrap(
        await apiClient.POST("/v1/workspaces/{workspace_id}/conversations", {
          params: { path: { workspace_id: workspaceId } },
          body: { assistant_id: assistantId },
        }),
      ),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: conversationListQueryKey(workspaceId) }),
  });
}

/** `DELETE /v1/workspaces/{id}/conversations/{conversation_id}` (204, owner only; audited). */
export function useDeleteConversation(workspaceId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (conversationId: string) => {
      unwrap(
        await apiClient.DELETE("/v1/workspaces/{workspace_id}/conversations/{conversation_id}", {
          params: { path: { workspace_id: workspaceId, conversation_id: conversationId } },
        }),
      );
    },
    onSuccess: async (_, conversationId) => {
      queryClient.removeQueries({ queryKey: conversationQueryKey(workspaceId, conversationId) });
      await queryClient.invalidateQueries({ queryKey: conversationListQueryKey(workspaceId) });
    },
  });
}

/** Reloads a conversation and the list (its title and position change with each question). */
export function refreshConversation(
  queryClient: QueryClient,
  workspaceId: string,
  conversationId: string,
) {
  return Promise.all([
    queryClient.invalidateQueries({ queryKey: conversationQueryKey(workspaceId, conversationId) }),
    queryClient.invalidateQueries({ queryKey: conversationListQueryKey(workspaceId) }),
  ]);
}

export interface FeedbackRequest {
  conversationId: string;
  messageId: string;
  feedback: FeedbackInput;
}

/**
 * `POST .../messages/{message_id}/feedback`: thumbs up or down with an optional comment; sending
 * again replaces it. The answer is written into the cached conversation.
 */
export function useSetFeedback(workspaceId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ conversationId, messageId, feedback }: FeedbackRequest) =>
      unwrap(
        await apiClient.POST(
          "/v1/workspaces/{workspace_id}/conversations/{conversation_id}/messages/{message_id}/feedback",
          {
            params: {
              path: {
                workspace_id: workspaceId,
                conversation_id: conversationId,
                message_id: messageId,
              },
            },
            body: feedback,
          },
        ),
      ),
    onSuccess: (saved, { conversationId, messageId }) => {
      queryClient.setQueryData<ConversationDetail>(
        conversationQueryKey(workspaceId, conversationId),
        (detail) =>
          detail && {
            ...detail,
            messages: {
              ...detail.messages,
              items: detail.messages.items.map((message) =>
                message.id === messageId ? { ...message, feedback: saved } : message,
              ),
            },
          },
      );
    },
  });
}
