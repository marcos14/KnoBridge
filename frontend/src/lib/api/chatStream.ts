import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";

import { type ChatEvent, parseChatEvent } from "./chatEvents";
import { apiClient, toApiError } from "./client";
import { type Citation, refreshConversation } from "./conversations";
import { readSseEvents } from "./sse";

/** How the answer being streamed ended; `null` while it is still arriving. */
export type ChatOutcome =
  | { kind: "done"; status: "completed" | "no_source" }
  | { kind: "error"; code: string }
  /** Stopped by the user, connection lost or stream cut: the server records `interrupted`. */
  | { kind: "interrupted" };

/** The question just sent and its answer as it arrives, until the conversation is reloaded. */
export interface PendingAnswer {
  conversationId: string;
  question: string;
  userMessageId: string | null;
  messageId: string | null;
  citations: Citation[];
  text: string;
  outcome: ChatOutcome | null;
}

export interface ChatFailure {
  conversationId: string;
  error: unknown;
}

export interface ChatStream {
  /** The exchange in progress, shown after the saved messages; `null` when idle. */
  pending: PendingAnswer | null;
  /** Why the last question did not go (JSON error before the stream, network), and where. */
  failure: ChatFailure | null;
  /**
   * Sends `content` to the conversation and streams the answer. Resolves `false` when the question
   * did not go (see `failure`) and `true` once the answer ended and the conversation was reloaded.
   */
  send: (conversationId: string, content: string) => Promise<boolean>;
  /** Stops the answer in progress; the server keeps what was generated as `interrupted`. */
  stop: () => void;
  /** Forgets `failure`: it belongs to the conversation the member just left. */
  clearFailure: () => void;
}

function applyEvent(pending: PendingAnswer, event: ChatEvent): PendingAnswer {
  switch (event.type) {
    case "citations":
      return {
        ...pending,
        messageId: event.messageId,
        userMessageId: event.userMessageId,
        citations: event.citations,
      };
    case "delta":
      return { ...pending, text: pending.text + event.text };
    case "done":
      return { ...pending, outcome: { kind: "done", status: event.status } };
    case "error":
      return { ...pending, outcome: { kind: "error", code: event.code } };
  }
}

/**
 * The single hook that talks Server-Sent Events with the chat (`docs/specs/chat-sse.md`): POSTs
 * the question with the session cookie and CSRF header (through `apiClient`), reads the body as a
 * stream and applies `citations`, `delta`, `done` and `error` as they come. Stopping aborts the
 * request; whatever way the answer ends (final event, stop, lost connection), the conversation is
 * reloaded, because the server is the source of truth for the saved message and its status.
 */
export function useChatStream(workspaceId: string): ChatStream {
  const queryClient = useQueryClient();
  const [pending, setPending] = useState<PendingAnswer | null>(null);
  const [failure, setFailure] = useState<ChatFailure | null>(null);
  const controllerRef = useRef<AbortController | null>(null);

  // Leaving the screen ends the stream, as closing the tab would.
  useEffect(
    () => () => {
      controllerRef.current?.abort();
    },
    [],
  );

  const update = useCallback((change: (current: PendingAnswer) => PendingAnswer) => {
    setPending((current) => (current === null ? current : change(current)));
  }, []);

  const send = useCallback(
    async (conversationId: string, content: string) => {
      if (controllerRef.current !== null) {
        return false;
      }
      const controller = new AbortController();
      controllerRef.current = controller;
      setFailure(null);
      setPending({
        conversationId,
        question: content,
        userMessageId: null,
        messageId: null,
        citations: [],
        text: "",
        outcome: null,
      });
      let sent = true;
      let answered = false;
      try {
        const {
          data,
          error: body,
          response,
        } = await apiClient.POST(
          "/v1/workspaces/{workspace_id}/conversations/{conversation_id}/messages",
          {
            params: { path: { workspace_id: workspaceId, conversation_id: conversationId } },
            body: { content },
            headers: { Accept: "text/event-stream" },
            parseAs: "stream",
            signal: controller.signal,
          },
        );
        answered = true;
        if (!response.ok) {
          sent = false;
          setFailure({ conversationId, error: toApiError(response.status, body) });
        } else if (data) {
          for await (const sse of readSseEvents(data, controller.signal)) {
            const event = parseChatEvent(sse);
            if (event !== null) {
              update((current) => applyEvent(current, event));
            }
          }
        }
      } catch (caught) {
        if (!answered && !controller.signal.aborted) {
          // No answer at all (network down): the question did not reach the server.
          sent = false;
          setFailure({ conversationId, error: caught });
        } else {
          // Lost connection or a stream the contract does not allow: stop it on both ends.
          controller.abort();
        }
      }
      update((current) =>
        current.outcome === null ? { ...current, outcome: { kind: "interrupted" } } : current,
      );
      controllerRef.current = null;
      if (sent) {
        await refreshConversation(queryClient, workspaceId, conversationId);
      }
      setPending(null);
      return sent;
    },
    [queryClient, update, workspaceId],
  );

  const stop = useCallback(() => {
    controllerRef.current?.abort();
  }, []);

  const clearFailure = useCallback(() => {
    setFailure(null);
  }, []);

  return { pending, failure, send, stop, clearFailure };
}
