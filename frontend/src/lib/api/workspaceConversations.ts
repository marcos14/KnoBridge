import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { apiClient, unwrap } from "./client";
import { MESSAGES_PAGE_SIZE } from "./conversations";
import type { ResponseLevel } from "./levels";
import type { components } from "./schema.gen";

/**
 * The conversations of every member and API key, as owners and admins see them
 * (`/admin/conversations`). A conversation of the API has no user: `api_key_*` names its key.
 */
export type WorkspaceConversation = components["schemas"]["AdminConversationOut"];
export type WorkspaceConversationDetail = components["schemas"]["AdminConversationDetailOut"];
export type WorkspaceMessage = components["schemas"]["AdminMessageOut"];
export type WorkspaceFeedback = components["schemas"]["AdminFeedbackOut"];
export type ConversationStats = components["schemas"]["ConversationStatsOut"];
export type ConversationChannel = components["schemas"]["ConversationChannel"];

/** A creation period as the API takes it: `[createdFrom, createdTo)`, ISO 8601 instants. */
export interface CreationPeriod {
  createdFrom?: string;
  createdTo?: string;
}

/** Filters and page of the workspace's conversations. */
export interface WorkspaceConversationsQuery extends CreationPeriod {
  productId?: string;
  level?: ResponseLevel;
  userId?: string;
  channel?: ConversationChannel;
  /** Only conversations with at least one thumbs down. */
  negativeFeedback?: boolean;
  limit: number;
  offset: number;
}

export function workspaceConversationsQueryKey(workspaceId: string) {
  return ["api", "workspaces", workspaceId, "admin", "conversations"] as const;
}

/** One page of the workspace's conversations, most recently active first (owner or admin). */
export function useWorkspaceConversations(workspaceId: string, query: WorkspaceConversationsQuery) {
  return useQuery({
    queryKey: [...workspaceConversationsQueryKey(workspaceId), "list", query],
    queryFn: async ({ signal }) =>
      unwrap(
        await apiClient.GET("/v1/workspaces/{workspace_id}/admin/conversations", {
          params: {
            path: { workspace_id: workspaceId },
            query: {
              product_id: query.productId,
              level: query.level,
              user_id: query.userId,
              channel: query.channel,
              created_from: query.createdFrom,
              created_to: query.createdTo,
              // `false` is the API default: leaving it out keeps the request as short as the filter.
              negative_feedback: query.negativeFeedback === true ? true : undefined,
              limit: query.limit,
              offset: query.offset,
            },
          },
          signal,
        }),
      ),
    placeholderData: keepPreviousData,
  });
}

/** Totals of the period (the API's default without one: the 30 days before now). */
export function useConversationStats(workspaceId: string, period: CreationPeriod) {
  return useQuery({
    queryKey: [...workspaceConversationsQueryKey(workspaceId), "stats", period],
    queryFn: async ({ signal }) =>
      unwrap(
        await apiClient.GET("/v1/workspaces/{workspace_id}/admin/conversations/stats", {
          params: {
            path: { workspace_id: workspaceId },
            query: { created_from: period.createdFrom, created_to: period.createdTo },
          },
          signal,
        }),
      ),
    placeholderData: keepPreviousData,
  });
}

/**
 * Any conversation of the workspace with all its messages and everyone's feedback. Long conversations are
 * read in pages of `MESSAGES_PAGE_SIZE` and joined.
 */
export function useWorkspaceConversation(workspaceId: string, conversationId: string) {
  return useQuery({
    queryKey: [...workspaceConversationsQueryKey(workspaceId), "detail", conversationId],
    queryFn: async ({ signal }) => {
      const read = async (offset: number) =>
        unwrap(
          await apiClient.GET(
            "/v1/workspaces/{workspace_id}/admin/conversations/{conversation_id}",
            {
              params: {
                path: { workspace_id: workspaceId, conversation_id: conversationId },
                query: { limit: MESSAGES_PAGE_SIZE, offset },
              },
              signal,
            },
          ),
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
      return {
        ...detail,
        messages: { ...detail.messages, items },
      } satisfies WorkspaceConversationDetail;
    },
  });
}
