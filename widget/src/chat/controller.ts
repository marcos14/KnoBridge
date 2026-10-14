// The visitor's conversation, without any rendering: restore from the browser pointer, create
// the conversation on the first question, stream the answer and turn failures into messages
// (docs/specs/widget.md, "Comportamento" and "Histórico no navegador").

import { ApiError, asApiError, isAbort, type WidgetApi } from "../api/client.ts";
import type { Citation, MessageStatus, WidgetMessage } from "../api/types.ts";
import type { ConversationStore } from "../lib/storage.ts";

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
}

/** What the controller needs from the element: events on the element and a re-render. */
export interface ChatHost {
  emit(name: string, detail: Record<string, unknown>): void;
  changed(): void;
}

interface Current {
  id: string;
  token: string;
}

function failureOf(error: ApiError): Failure {
  if (error.code === "rate_limited") {
    return { kind: "rate_limited", minutes: Math.max(1, Math.ceil((error.retryAfter ?? 60) / 60)) };
  }
  if (error.code === "widget_unavailable") return { kind: "unavailable" };
  return { kind: "failed" };
}

export class ChatController {
  messages: ViewMessage[] = [];
  busy = false;
  private current: Current | null = null;
  private abortController: AbortController | null = null;
  private sequence = 0;
  private readonly api: WidgetApi;
  private readonly store: ConversationStore;
  private readonly host: ChatHost;
  private readonly identitySub: () => string | null;
  private readonly now: () => Date;

  constructor(
    api: WidgetApi,
    store: ConversationStore,
    host: ChatHost,
    identitySub: () => string | null,
    now: () => Date = () => new Date(),
  ) {
    this.api = api;
    this.store = store;
    this.host = host;
    this.identitySub = identitySub;
    this.now = now;
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
    };
  }

  /** Reopens the stored conversation of the same visitor; 401 or 404 forgets the pointer. */
  async restore(): Promise<void> {
    const entry = this.store.load();
    // Another person (or anonymous versus identified) never sees this conversation.
    if (!entry) return;
    if (entry.identity_sub !== this.identitySub()) return;
    // The composer waits for the history, so a question never races the restored conversation.
    this.busy = true;
    this.host.changed();
    try {
      const detail = await this.api.conversation(entry.conversation_id, entry.visitor_token);
      this.current = { id: entry.conversation_id, token: entry.visitor_token };
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

  private async ensureConversation(signal: AbortSignal): Promise<Current> {
    if (this.current) return this.current;
    const created = await this.api.createConversation(signal);
    // "Nova conversa" during the creation: this conversation must not be remembered.
    signal.throwIfAborted();
    this.current = { id: created.conversation.id, token: created.visitor_token };
    this.store.save({
      conversation_id: created.conversation.id,
      visitor_token: created.visitor_token,
      identity_sub: this.identitySub(),
      saved_at: this.now().toISOString(),
    });
    return this.current;
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
    this.store.clear();
    this.current = null;
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
