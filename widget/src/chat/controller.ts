// The visitor's conversation, without any rendering: restore from the browser pointer, create
// the conversation on the first question (with the signed identity, when there is one), stream the
// answer and turn failures into messages (docs/specs/widget.md, "Comportamento" and "Histórico no
// navegador").

import { ApiError, asApiError, isAbort, type WidgetApi } from "../api/client.ts";
import type {
  Citation,
  Feedback,
  MessageStatus,
  TicketRequest,
  Visitor,
  WidgetConversation,
  WidgetMessage,
} from "../api/types.ts";
import { identitySub } from "../lib/identity.ts";
import type { ConversationStore } from "../lib/storage.ts";
import { AnswerActions } from "./actions.ts";

export type Failure =
  { kind: "failed" } | { kind: "rate_limited"; minutes: number } | { kind: "unavailable" };

export interface ViewMessage {
  /** Stable key for rendering and element ids; the server id may arrive later. */
  key: string;
  id: string | null;
  role: "user" | "assistant";
  content: string;
  status: MessageStatus;
  citations: Citation[];
  failure: Failure | null;
  /** The question an assistant message answers, to resend it on "Tentar de novo". */
  question: string | null;
  feedback: Feedback | null;
  ticketRequest: TicketRequest | null;
}

/** What the controller needs from the element: events on the element and a re-render. */
export interface ChatHost {
  emit(name: string, detail: Record<string, unknown>): void;
  changed(): void;
}

/** The conversation the widget talks to: its id and the visitor token that authorizes it. */
export interface Session {
  id: string;
  token: string;
}

export function failureOf(error: ApiError): Failure {
  if (error.code === "rate_limited") {
    return { kind: "rate_limited", minutes: Math.max(1, Math.ceil((error.retryAfter ?? 60) / 60)) };
  }
  if (error.code === "widget_unavailable") return { kind: "unavailable" };
  return { kind: "failed" };
}

export class ChatController {
  messages: ViewMessage[] = [];
  busy = false;
  /** Name and e-mail of the signed identity, as the server verified them. */
  visitor: Visitor | null = null;
  /** Whether the conversation offers tickets; null until the server says. */
  ticketEnabled: boolean | null = null;
  /** Feedback and tickets on the answers of this conversation. */
  readonly actions: AnswerActions;
  private current: Session | null = null;
  private abortController: AbortController | null = null;
  private sequence = 0;
  private sub: string | null;
  private readonly api: WidgetApi;
  private readonly store: ConversationStore;
  private readonly host: ChatHost;
  private readonly identity: () => string | null;
  private readonly now: () => Date;

  constructor(
    api: WidgetApi,
    store: ConversationStore,
    host: ChatHost,
    identity: () => string | null,
    now: () => Date = () => new Date(),
  ) {
    this.api = api;
    this.store = store;
    this.host = host;
    this.identity = identity;
    this.now = now;
    this.sub = identitySub(identity());
    this.actions = new AnswerActions(api, this, host);
  }

  get session(): Session | null {
    return this.current;
  }

  private nextKey(): string {
    this.sequence += 1;
    return `m${String(this.sequence)}`;
  }

  private fromServer(message: WidgetMessage, previous: WidgetMessage | undefined): ViewMessage {
    const failed = message.role === "assistant" && message.status === "failed";
    return {
      key: this.nextKey(),
      id: message.id,
      role: message.role,
      content: message.content,
      status: message.status,
      citations: message.citations,
      failure: failed ? { kind: "failed" } : null,
      question: previous?.role === "user" ? previous.content : null,
      feedback: message.feedback,
      ticketRequest: message.ticket_request,
    };
  }

  private adopt(session: Session, conversation: WidgetConversation): void {
    this.current = session;
    this.visitor = conversation.visitor;
    this.ticketEnabled = conversation.ticket_enabled;
  }

  /** Reopens the stored conversation of the same visitor; 401 or 404 forgets the pointer. */
  async restore(): Promise<void> {
    const entry = this.store.load();
    // Another person (or anonymous versus identified) never sees this conversation.
    if (!entry) return;
    if (entry.identity_sub !== this.sub) return;
    // The composer waits for the history, so a question never races the restored conversation.
    this.busy = true;
    this.host.changed();
    try {
      const detail = await this.api.conversation(entry.conversation_id, entry.visitor_token);
      // The identity changed while the history was on its way: it belongs to someone else.
      if (entry.identity_sub !== this.sub) return;
      this.adopt({ id: entry.conversation_id, token: entry.visitor_token }, detail);
      this.messages = detail.messages.map((message, i) =>
        this.fromServer(message, detail.messages[i - 1]),
      );
      this.host.changed();
    } catch (error) {
      const apiError = asApiError(error);
      if (apiError.status === 401 || apiError.code === "not_found") this.store.clear();
      this.host.emit("knobridge-error", { code: apiError.code, status: apiError.status });
    } finally {
      this.busy = false;
      this.host.changed();
    }
  }

  /** The identity changed: with another `sub`, this conversation is put away and the next opens. */
  async identityChanged(): Promise<void> {
    const sub = identitySub(this.identity());
    if (sub === this.sub) return;
    this.sub = sub;
    this.abort();
    this.actions.reset();
    this.current = null;
    this.visitor = null;
    this.ticketEnabled = null;
    this.messages = [];
    this.host.changed();
    // The new visitor may have a conversation of their own in this browser.
    await this.restore();
  }

  private async ensureConversation(signal: AbortSignal): Promise<Session> {
    if (this.current) return this.current;
    const sub = this.sub;
    const created = await this.api.createConversation(this.identity(), signal);
    // "Nova conversa" during the creation: this conversation must not be remembered.
    signal.throwIfAborted();
    const session = { id: created.conversation.id, token: created.visitor_token };
    this.adopt(session, created.conversation);
    this.store.save({
      conversation_id: session.id,
      visitor_token: session.token,
      identity_sub: sub,
      saved_at: this.now().toISOString(),
    });
    return session;
  }

  async send(question: string): Promise<void> {
    if (this.busy) return;
    this.busy = true;
    const user: ViewMessage = {
      key: this.nextKey(),
      id: null,
      role: "user",
      content: question,
      status: "completed",
      citations: [],
      failure: null,
      question: null,
      feedback: null,
      ticketRequest: null,
    };
    const answer: ViewMessage = {
      ...user,
      key: this.nextKey(),
      role: "assistant",
      content: "",
      status: "streaming",
      question,
    };
    // Replaced, not mutated, so Lit sees the new array; the objects inside are mutated in place.
    this.messages = [...this.messages, user, answer];
    this.host.changed();
    const abort = new AbortController();
    this.abortController = abort;
    let conversationId: string | null = null;
    try {
      const current = await this.ensureConversation(abort.signal);
      conversationId = current.id;
      for await (const event of this.api.send(current.id, current.token, question, abort.signal)) {
        if (event.type === "citations") {
          answer.id = event.data.message_id;
          user.id = event.data.user_message_id;
          answer.citations = event.data.citations;
          this.host.emit("knobridge-message-sent", { conversationId, messageId: answer.id });
        } else if (event.type === "delta") {
          answer.content += event.data.text;
        } else if (event.type === "done") {
          answer.status = event.data.status;
          this.ticketEnabled = event.data.ticket_requests_enabled;
        } else {
          answer.status = "failed";
          answer.failure = { kind: "failed" };
          this.host.emit("knobridge-error", { code: event.data.error.code, status: null });
        }
        this.host.changed();
      }
      this.host.emit("knobridge-answer", {
        conversationId,
        messageId: answer.id,
        status: answer.status,
        citations: answer.citations.length,
      });
    } catch (error) {
      if (isAbort(error)) return;
      const apiError = asApiError(error);
      if (apiError.status === 401 || apiError.code === "not_found") {
        // The conversation is gone (deleted, or the token no longer matches): start over.
        this.current = null;
        this.store.clear();
      }
      answer.status = "failed";
      answer.failure = failureOf(apiError);
      this.host.emit("knobridge-error", { code: apiError.code, status: apiError.status });
      if (conversationId !== null && answer.id !== null) {
        this.host.emit("knobridge-answer", {
          conversationId,
          messageId: answer.id,
          status: answer.status,
          citations: answer.citations.length,
        });
      }
    } finally {
      if (this.abortController === abort) {
        this.abortController = null;
        this.busy = false;
        this.host.changed();
      }
    }
  }

  /** Removes the failed answer and its question, then asks again. */
  async retry(key: string): Promise<void> {
    const index = this.messages.findIndex((message) => message.key === key);
    const answer = this.messages[index];
    if (!answer?.question || this.busy) return;
    // An answer has a question only when the message before it is that question.
    this.messages = [...this.messages.slice(0, index - 1), ...this.messages.slice(index + 1)];
    await this.send(answer.question);
  }

  /** "Nova conversa": stops a running answer and forgets the pointer in the browser. */
  reset(): void {
    this.abort();
    this.actions.reset();
    this.store.clear();
    this.current = null;
    this.visitor = null;
    this.ticketEnabled = null;
    this.messages = [];
    this.busy = false;
    this.host.changed();
  }

  /** Stops a running answer (element removed from the page): it stays as `interrupted`. */
  abort(): void {
    if (!this.abortController) return;
    this.abortController.abort();
    this.abortController = null;
    this.busy = false;
    for (const message of this.messages) {
      if (message.status === "streaming") message.status = "interrupted";
    }
    this.host.changed();
  }
}
