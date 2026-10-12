import { type QueryClient, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiClient, isApiErrorCode, unwrap } from "./client";
import { type ConversationDetail, conversationQueryKey } from "./conversations";
import type { components } from "./schema.gen";

export type TicketRequest = components["schemas"]["TicketRequestOut"];
export type TicketRequestPreview = components["schemas"]["TicketRequestPreviewOut"];

/**
 * How often a pending request is read again. A delivery takes seconds when the destination is up
 * and retries for up to 24 hours when it is not, so a few seconds is enough.
 */
export const TICKET_REQUEST_POLL_INTERVAL_MS = 3000;

/** The assistant answer a ticket is asked for. */
export interface TicketRequestTarget {
  conversationId: string;
  messageId: string;
}

export function ticketRequestQueryKey(workspaceId: string, requestId: string) {
  return ["api", "workspaces", workspaceId, "ticket-requests", requestId] as const;
}

/** Writes `request` on its message in the cached conversation, so the thread shows its state. */
function storeRequest(queryClient: QueryClient, workspaceId: string, request: TicketRequest) {
  queryClient.setQueryData<ConversationDetail>(
    conversationQueryKey(workspaceId, request.conversation_id),
    (detail) =>
      detail && {
        ...detail,
        messages: {
          ...detail.messages,
          items: detail.messages.items.map((message) =>
            message.id === request.message_id ? { ...message, ticket_request: request } : message,
          ),
        },
      },
  );
}

/**
 * `POST .../conversations/{id}/ticket-requests/preview` (the conversation's owner): what would be
 * sent (question, summary written by the assistant's model, requester and messages). Writes
 * nothing. 409 `ticket_request_exists`, `ticket_webhook_not_configured`, `assistant_inactive`;
 * 422 `validation_error` for an answer that cannot be asked for.
 */
export function usePreviewTicketRequest(workspaceId: string) {
  return useMutation({
    mutationFn: async ({ conversationId, messageId }: TicketRequestTarget) =>
      unwrap(
        await apiClient.POST(
          "/v1/workspaces/{workspace_id}/conversations/{conversation_id}/ticket-requests/preview",
          {
            params: { path: { workspace_id: workspaceId, conversation_id: conversationId } },
            body: { message_id: messageId },
          },
        ),
      ),
  });
}

export interface TicketRequestCreation extends TicketRequestTarget {
  /** The summary as the member left it (1 to 2000 characters). */
  summary: string;
}

/**
 * `POST .../conversations/{id}/ticket-requests` (202): records the request `pending` and starts
 * its delivery; the answer goes on its message in the cached conversation. A request that
 * already exists (409 `ticket_request_exists`) reloads the conversation, which brings it.
 */
export function useCreateTicketRequest(workspaceId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ conversationId, messageId, summary }: TicketRequestCreation) =>
      unwrap(
        await apiClient.POST(
          "/v1/workspaces/{workspace_id}/conversations/{conversation_id}/ticket-requests",
          {
            params: { path: { workspace_id: workspaceId, conversation_id: conversationId } },
            body: { message_id: messageId, summary },
          },
        ),
      ),
    onSuccess: (request) => {
      storeRequest(queryClient, workspaceId, request);
    },
    onError: async (error, { conversationId }) => {
      if (isApiErrorCode(error, "ticket_request_exists")) {
        await queryClient.invalidateQueries({
          queryKey: conversationQueryKey(workspaceId, conversationId),
        });
      }
    },
  });
}

/**
 * The state of `request` (`GET .../ticket-requests/{id}`), read again every
 * `TICKET_REQUEST_POLL_INTERVAL_MS` while it is `pending` and never after: delivered and failed
 * are final. The newest state also goes on its message in the cached conversation.
 */
export function useTicketRequest(workspaceId: string, request: TicketRequest) {
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: ticketRequestQueryKey(workspaceId, request.id),
    queryFn: async ({ signal }) => {
      const current = unwrap(
        await apiClient.GET(
          "/v1/workspaces/{workspace_id}/conversations/{conversation_id}/ticket-requests/{request_id}",
          {
            params: {
              path: {
                workspace_id: workspaceId,
                conversation_id: request.conversation_id,
                request_id: request.id,
              },
            },
            signal,
          },
        ),
      );
      storeRequest(queryClient, workspaceId, current);
      return current;
    },
    initialData: request,
    // What the conversation brought is fresh: the first read waits for the interval.
    staleTime: TICKET_REQUEST_POLL_INTERVAL_MS,
    enabled: request.status === "pending",
    refetchInterval: (current) =>
      current.state.data?.status === "pending" ? TICKET_REQUEST_POLL_INTERVAL_MS : false,
  });
  // A conversation reloaded after the request finished is newer than a stale pending read.
  return request.status === "pending" ? query.data : request;
}
