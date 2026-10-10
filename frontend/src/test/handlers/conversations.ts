import { http, HttpResponse } from "msw";

import type {
  Citation,
  Conversation,
  ConversationDetail,
  FeedbackInput,
  Message,
  MessageStatus,
} from "@/lib/api/conversations";

import {
  makeConversation,
  makeConversationDetail,
  makeConversations,
  makeMessage,
  makeQuestion,
  messageId,
} from "../factories";
import { apiErrorResponse } from "./errors";
import { page } from "./page";

const CONVERSATIONS = "*/v1/workspaces/:workspaceId/conversations";
const CONVERSATION = "*/v1/workspaces/:workspaceId/conversations/:conversationId";
const MESSAGES = "*/v1/workspaces/:workspaceId/conversations/:conversationId/messages";
const FEEDBACK =
  "*/v1/workspaces/:workspaceId/conversations/:conversationId/messages/:messageId/feedback";

const encoder = new TextEncoder();

/** One SSE frame as the backend writes it: `event:` line, one-line JSON `data:`, blank line. */
export function sseFrame(event: string, data: unknown): string {
  return `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
}

export interface AnswerScript {
  messageId?: string;
  userMessageId?: string;
  citations?: Citation[];
  deltas?: string[];
  /** Final event: `done` with this status, or `error` with this code. */
  end?: { status: "completed" | "no_source" } | { error: string };
}

/** The frames of a whole answer, in the contract's order: citations, deltas, done or error. */
export function answerFrames({
  messageId: answerId = messageId(902),
  userMessageId = messageId(901),
  citations = [],
  deltas = [],
  end = { status: "completed" },
}: AnswerScript = {}): string[] {
  const final =
    "status" in end
      ? sseFrame("done", {
          message_id: answerId,
          status: end.status,
          model: end.status === "completed" ? "gpt-4.1-mini" : null,
          input_tokens: null,
          output_tokens: null,
          latency_ms: 10,
        })
      : sseFrame("error", {
          message_id: answerId,
          status: "failed",
          error: { code: end.error, message: "Synthetic error.", details: null },
        });
  return [
    sseFrame("citations", { message_id: answerId, user_message_id: userMessageId, citations }),
    ...deltas.map((text) => sseFrame("delta", { text })),
    final,
  ];
}

/** A `text/event-stream` response whose body is `body` (whole text or a stream of bytes). */
export function sseResponse(body: string | ReadableStream<Uint8Array>) {
  return new HttpResponse(typeof body === "string" ? encoder.encode(body) : body, {
    status: 200,
    headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-cache" },
  });
}

/** A stream of bytes that each test feeds by hand: no timers, every chunk arrives when pushed. */
export function controlledStream() {
  let controller!: ReadableStreamDefaultController<Uint8Array>;
  const stream = new ReadableStream<Uint8Array>({
    start(streamController) {
      controller = streamController;
    },
  });
  return {
    stream,
    push: (text: string) => {
      controller.enqueue(encoder.encode(text));
    },
    close: () => {
      controller.close();
    },
    fail: (error: Error) => {
      controller.error(error);
    },
  };
}

/** GET /v1/workspaces/{id}/conversations listing `conversations` (default: two). */
export function conversationsAs(conversations: Conversation[] = makeConversations()) {
  return http.get(CONVERSATIONS, ({ request }) => page(request, conversations));
}

/** GET /v1/workspaces/{id}/conversations/{conversation_id} answering `detail`. */
export function conversationAs(detail: ConversationDetail = makeConversationDetail()) {
  return http.get(CONVERSATION, () => HttpResponse.json<ConversationDetail>(detail));
}

/** What a reply handler returns: the stream to send and the answer saved for the next reload. */
export interface ChatReply {
  body: string | ReadableStream<Uint8Array>;
  /** Saved assistant message (content, status, citations); default: completed "Resposta.". */
  saved?: Partial<Message>;
}

interface ChatStoreOptions {
  conversations?: Conversation[];
  /** Messages per conversation id (default: none). */
  messages?: Record<string, Message[]>;
  /** Answer to each question; default: a completed "Resposta." without sources. */
  reply?: (question: string, conversationId: string) => ChatReply | Response;
}

/**
 * Conversations and messages that really change, like the backend: `POST` creates a conversation
 * (409 `assistant_inactive` for an assistant id in `inactive`), `DELETE` removes it, a question is
 * saved with its answer (and names an untitled conversation) before the reply streams, and
 * feedback is stored on the message. `created`, `deleted`, `questions` and `feedback` keep what
 * was asked, in order.
 */
export function chatStore({
  conversations: initial = makeConversations(),
  messages: initialMessages = {},
  reply = () => ({ body: answerFrames({ deltas: ["Resposta."] }).join("") }),
}: ChatStoreOptions = {}) {
  let conversations = [...initial];
  const threads = new Map<string, Message[]>(Object.entries(initialMessages));
  const created: string[] = [];
  const deleted: string[] = [];
  const questions: { conversationId: string; content: string }[] = [];
  const feedback: { messageId: string; body: FeedbackInput }[] = [];
  let sequence = 0;
  const find = (id: string) => conversations.find((item) => item.id === id);
  const detail = (conversation: Conversation) =>
    makeConversationDetail(conversation, threads.get(conversation.id) ?? []);

  const handlers = [
    http.get(CONVERSATIONS, ({ request }) => page(request, conversations)),
    http.post(CONVERSATIONS, async ({ request }) => {
      const { assistant_id: assistantId } = (await request.json()) as { assistant_id: string };
      const conversation = makeConversation({
        id: `00000000-0000-4000-8000-${String(990 + created.length).padStart(12, "0")}`,
        assistant_id: assistantId,
        title: null,
      });
      conversations = [conversation, ...conversations];
      created.push(assistantId);
      return HttpResponse.json<Conversation>(conversation, { status: 201 });
    }),
    http.get(CONVERSATION, ({ params }) => {
      const conversation = find(String(params.conversationId));
      return conversation === undefined
        ? apiErrorResponse(404, "not_found")
        : HttpResponse.json<ConversationDetail>(detail(conversation));
    }),
    http.delete(CONVERSATION, ({ params }) => {
      const conversationId = String(params.conversationId);
      if (find(conversationId) === undefined) {
        return apiErrorResponse(404, "not_found");
      }
      conversations = conversations.filter((item) => item.id !== conversationId);
      deleted.push(conversationId);
      return new HttpResponse(null, { status: 204 });
    }),
    http.post(MESSAGES, async ({ params, request }) => {
      const conversationId = String(params.conversationId);
      const conversation = find(conversationId);
      if (conversation === undefined) {
        return apiErrorResponse(404, "not_found");
      }
      const { content } = (await request.json()) as { content: string };
      questions.push({ conversationId, content });
      const answer = reply(content, conversationId);
      if (answer instanceof Response) {
        return answer;
      }
      sequence += 1;
      const userMessageId = messageId(900 + sequence * 2 - 1);
      const answerId = messageId(900 + sequence * 2);
      threads.set(conversationId, [
        ...(threads.get(conversationId) ?? []),
        makeQuestion(content, userMessageId),
        makeMessage({ id: answerId, content: "Resposta.", ...answer.saved }),
      ]);
      const updated = { ...conversation, title: conversation.title ?? content };
      conversations = [updated, ...conversations.filter((item) => item.id !== conversationId)];
      return sseResponse(answer.body);
    }),
    http.post(FEEDBACK, async ({ params, request }) => {
      const body = (await request.json()) as FeedbackInput;
      const id = String(params.messageId);
      const saved = { ...body, updated_at: "2026-10-10T12:00:00Z" };
      for (const [conversationId, thread] of threads) {
        threads.set(
          conversationId,
          thread.map((message) => (message.id === id ? { ...message, feedback: saved } : message)),
        );
      }
      feedback.push({ messageId: id, body });
      return HttpResponse.json(saved);
    }),
  ];
  return { handlers, created, deleted, questions, feedback };
}

/** Ids `chatStore` gives the `n`-th exchange (question and answer), to script matching frames. */
export function exchangeIds(n: number) {
  return { userMessageId: messageId(900 + n * 2 - 1), messageId: messageId(900 + n * 2) };
}

/** A saved answer with `status` (and `content`), for `ChatReply.saved`. */
export function savedAnswer(
  status: MessageStatus,
  content = "Resposta.",
  extra: Partial<Message> = {},
) {
  return { status, content, ...extra };
}

/** POST .../conversations refused with `status` and `code`. */
export function createConversationFails(status: number, code: string) {
  return http.post(CONVERSATIONS, () => apiErrorResponse(status, code));
}

/** GET .../conversations failing on the server (500). */
export const conversationsServerError = http.get(CONVERSATIONS, () =>
  apiErrorResponse(500, "internal_error"),
);

/** GET .../conversations/{id} failing on the server (500). */
export const conversationServerError = http.get(CONVERSATION, () =>
  apiErrorResponse(500, "internal_error"),
);

/** DELETE .../conversations/{id} refused with `status` and `code`. */
export function deleteConversationFails(status: number, code: string) {
  return http.delete(CONVERSATION, () => apiErrorResponse(status, code));
}

/** POST .../feedback refused with `status` and `code`. */
export function feedbackFails(status: number, code: string) {
  return http.post(FEEDBACK, () => apiErrorResponse(status, code));
}

/** POST .../messages answered by `respond` (an SSE response or a JSON error). */
export function messagesRespond(respond: (request: Request) => Response | Promise<Response>) {
  return http.post(MESSAGES, ({ request }) => respond(request));
}

/** Default chat handlers, without state: two conversations, the default thread, completed answers. */
export const conversationsHandlers = [
  conversationsAs(),
  conversationAs(),
  http.post(CONVERSATIONS, () =>
    HttpResponse.json<Conversation>(makeConversation({ title: null }), { status: 201 }),
  ),
  http.delete(CONVERSATION, () => new HttpResponse(null, { status: 204 })),
  messagesRespond(() => sseResponse(answerFrames({ deltas: ["Resposta."] }).join(""))),
  http.post(FEEDBACK, async ({ request }) =>
    HttpResponse.json({
      ...((await request.json()) as FeedbackInput),
      updated_at: "2026-10-10T12:00:00Z",
    }),
  ),
];
