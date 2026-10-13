import { http, HttpResponse } from "msw";

import type {
  Citation,
  Conversation,
  ConversationDetail,
  FeedbackInput,
  Message,
  MessageStatus,
} from "@/lib/api/conversations";
import type { components } from "@/lib/api/schema.gen";
import type { TicketRequest, TicketRequestPreview } from "@/lib/api/ticketRequests";

import {
  makeConversation,
  makeConversationDetail,
  makeConversations,
  makeMessage,
  makeQuestion,
  messageId,
} from "../factories";
import { makeTicketRequest, makeTicketRequestPreview, TICKET_REQUEST_ID } from "../ticketFactories";
import { apiErrorResponse } from "./errors";
import { page } from "./page";

const CONVERSATIONS = "*/v1/workspaces/:workspaceId/conversations";
const CONVERSATION = "*/v1/workspaces/:workspaceId/conversations/:conversationId";
const MESSAGES = "*/v1/workspaces/:workspaceId/conversations/:conversationId/messages";
const FEEDBACK =
  "*/v1/workspaces/:workspaceId/conversations/:conversationId/messages/:messageId/feedback";
const TICKET_REQUESTS =
  "*/v1/workspaces/:workspaceId/conversations/:conversationId/ticket-requests";
const TICKET_PREVIEW = `${TICKET_REQUESTS}/preview`;
const TICKET_REQUEST = `${TICKET_REQUESTS}/:requestId`;

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
  /** `ticket_requests_enabled` of the `done` event (v0.7; default `false`). */
  ticketRequestsEnabled?: boolean;
}

/** The frames of a whole answer, in the contract's order: citations, deltas, done or error. */
export function answerFrames({
  messageId: answerId = messageId(902),
  userMessageId = messageId(901),
  citations = [],
  deltas = [],
  end = { status: "completed" },
  ticketRequestsEnabled = false,
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
          ticket_requests_enabled: ticketRequestsEnabled,
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

/** Body of `POST .../conversations`. */
export type ConversationInput = components["schemas"]["ConversationCreate"];

/** The conversations matching the `product_id` and `level` filters of the request, as the API. */
function filterConversations(request: Request, conversations: readonly Conversation[]) {
  const params = new URL(request.url).searchParams;
  const productId = params.get("product_id");
  const level = params.get("level");
  return conversations.filter(
    (item) =>
      (productId === null || item.product_id === productId) &&
      (level === null || item.level === level),
  );
}

/** GET /v1/workspaces/{id}/conversations listing `conversations` (default: two), filtered. */
export function conversationsAs(conversations: Conversation[] = makeConversations()) {
  return http.get(CONVERSATIONS, ({ request }) =>
    page(request, filterConversations(request, conversations)),
  );
}

/** GET /v1/workspaces/{id}/conversations recording each query string (`queries`). */
export function conversationsRecorder(conversations: Conversation[] = makeConversations()) {
  const queries: string[] = [];
  return {
    queries,
    handler: http.get(CONVERSATIONS, ({ request }) => {
      queries.push(new URL(request.url).search);
      return page(request, filterConversations(request, conversations));
    }),
  };
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
  /** `ticket_requests_enabled` of every conversation detail (default: `false`). */
  ticketRequestsEnabled?: boolean;
  /** Answer of the ticket preview of an answer; default `makeTicketRequestPreview`. */
  ticketPreview?: (messageId: string) => TicketRequestPreview | Response;
}

/**
 * Conversations and messages that really change, like the backend: `POST` creates a conversation
 * (409 `assistant_inactive` for an assistant id in `inactive`), `DELETE` removes it, a question is
 * saved with its answer (and names an untitled conversation) before the reply streams, and
 * feedback is stored on the message. A ticket request is stored on its answer (`pending`; 409
 * `ticket_request_exists` for a second one) and `settleTicket` moves it on, as the delivery would.
 * `created`, `deleted`, `questions`, `feedback`, `ticketPreviews` and `ticketCreations` keep what
 * was asked, in order; `ticketReads()` counts the reads of a request.
 */
export function chatStore({
  conversations: initial = makeConversations(),
  messages: initialMessages = {},
  reply = () => ({ body: answerFrames({ deltas: ["Resposta."] }).join("") }),
  ticketRequestsEnabled = false,
  ticketPreview = (id) => makeTicketRequestPreview({ message_id: id }),
}: ChatStoreOptions = {}) {
  let conversations = [...initial];
  const threads = new Map<string, Message[]>(Object.entries(initialMessages));
  const created: ConversationInput[] = [];
  const deleted: string[] = [];
  const questions: { conversationId: string; content: string }[] = [];
  const feedback: { messageId: string; body: FeedbackInput }[] = [];
  const ticketPreviews: string[] = [];
  const ticketCreations: { messageId: string; summary: string }[] = [];
  // Requests already on the initial messages exist on the "server" too.
  const requests = new Map<string, TicketRequest>(
    Object.values(initialMessages)
      .flat()
      .flatMap((message) => (message.ticket_request ? [message.ticket_request] : []))
      .map((request) => [request.id, request]),
  );
  let ticketReads = 0;
  let sequence = 0;
  const find = (id: string) => conversations.find((item) => item.id === id);
  const detail = (conversation: Conversation) => ({
    ...makeConversationDetail(conversation, threads.get(conversation.id) ?? []),
    ticket_requests_enabled: ticketRequestsEnabled,
  });
  const updateMessage = (id: string, change: (message: Message) => Message) => {
    for (const [conversationId, thread] of threads) {
      threads.set(
        conversationId,
        thread.map((message) => (message.id === id ? change(message) : message)),
      );
    }
  };
  const storeRequest = (request: TicketRequest) => {
    requests.set(request.id, request);
    updateMessage(request.message_id, (message) => ({ ...message, ticket_request: request }));
  };
  /** Moves the request on (default: the only one) with `changes`, as the delivery would. */
  const settleTicket = (changes: Partial<TicketRequest>, requestId = TICKET_REQUEST_ID) => {
    const request = requests.get(requestId);
    if (request === undefined) {
      throw new Error(`No ticket request ${requestId}`);
    }
    storeRequest({ ...request, ...changes });
  };

  const handlers = [
    http.get(CONVERSATIONS, ({ request }) =>
      page(request, filterConversations(request, conversations)),
    ),
    http.post(CONVERSATIONS, async ({ request }) => {
      const body = (await request.json()) as ConversationInput;
      const conversation = makeConversation({
        id: `00000000-0000-4000-8000-${String(990 + created.length).padStart(12, "0")}`,
        product_id: body.product_id,
        // Without a level the server uses the member's maximum; the default member is an owner.
        level: body.level ?? "product_dev",
        title: null,
      });
      conversations = [conversation, ...conversations];
      created.push(body);
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
      updateMessage(id, (message) => ({ ...message, feedback: saved }));
      feedback.push({ messageId: id, body });
      return HttpResponse.json(saved);
    }),
    http.post(TICKET_PREVIEW, async ({ request }) => {
      const { message_id: id } = (await request.json()) as { message_id: string };
      ticketPreviews.push(id);
      const answer = ticketPreview(id);
      return answer instanceof Response ? answer : HttpResponse.json<TicketRequestPreview>(answer);
    }),
    http.post(TICKET_REQUESTS, async ({ params, request }) => {
      const body = (await request.json()) as { message_id: string; summary: string };
      const existing = [...requests.values()].find((item) => item.message_id === body.message_id);
      if (existing !== undefined) {
        return apiErrorResponse(409, "ticket_request_exists", {
          ticket_request_id: existing.id,
        });
      }
      ticketCreations.push({ messageId: body.message_id, summary: body.summary });
      const stored = makeTicketRequest({
        id:
          requests.size === 0 ? TICKET_REQUEST_ID : `${TICKET_REQUEST_ID}-${String(requests.size)}`,
        conversation_id: String(params.conversationId),
        message_id: body.message_id,
      });
      storeRequest(stored);
      return HttpResponse.json<TicketRequest>(stored, { status: 202 });
    }),
    http.get(TICKET_REQUEST, ({ params }) => {
      ticketReads += 1;
      const found = requests.get(String(params.requestId));
      return found === undefined
        ? apiErrorResponse(404, "not_found")
        : HttpResponse.json<TicketRequest>(found);
    }),
  ];
  return {
    handlers,
    created,
    deleted,
    questions,
    feedback,
    ticketPreviews,
    ticketCreations,
    ticketReads: () => ticketReads,
    settleTicket,
  };
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
export function createConversationFails(status: number, code: string, details: unknown = null) {
  return http.post(CONVERSATIONS, () => apiErrorResponse(status, code, details));
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
