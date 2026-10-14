// What a visitor does with a finished answer (docs/specs/widget.md, "Comportamento"): 👍/👎 with an
// optional comment on 👎, and "Abrir chamado" with a summary, the e-mail when the signed identity
// has none, and the request followed every 10 s, at most 6 times, until the number arrives.
// The per-answer state of the forms lives here, by message key; rendering is in ../element/.

import { asApiError, type ApiError, type WidgetApi } from "../api/client.ts";
import type { Rating } from "../api/types.ts";
import type { ChatController, ChatHost, Session, ViewMessage } from "./controller.ts";

export type ActionError =
  | { kind: "failed" }
  | { kind: "rate_limited"; minutes: number }
  | { kind: "exists" }
  | { kind: "unavailable" }
  | { kind: "invalid" };

export type TicketField = "summary" | "email" | "name";

export interface TicketDraft {
  summary: string;
  email: string;
  name: string;
}

export interface AnswerState {
  feedbackBusy: boolean;
  feedbackError: ActionError | null;
  commentOpen: boolean;
  comment: string;
  commentSent: boolean;
  ticketOpen: boolean;
  ticketBusy: boolean;
  ticketError: ActionError | null;
  draft: TicketDraft;
  /** Fields refused by the local check, in the order of the form. */
  invalid: TicketField[];
}

/** Runs `task` after `ms`; returns the function that cancels it. */
export type Scheduler = (task: () => void, ms: number) => () => void;

export const POLL_INTERVAL_MS = 10_000;
export const POLL_ATTEMPTS = 6;
export const COMMENT_MAX_CHARS = 2000;
export const SUMMARY_MAX_CHARS = 2000;
export const NAME_MAX_CHARS = 200;
const EMAIL_MAX_CHARS = 320;
const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

const defaultScheduler: Scheduler = (task, ms) => {
  const id = setTimeout(task, ms);
  return () => {
    clearTimeout(id);
  };
};

function emptyState(): AnswerState {
  return {
    feedbackBusy: false,
    feedbackError: null,
    commentOpen: false,
    comment: "",
    commentSent: false,
    ticketOpen: false,
    ticketBusy: false,
    ticketError: null,
    draft: { summary: "", email: "", name: "" },
    invalid: [],
  };
}

function actionError(error: ApiError): ActionError {
  switch (error.code) {
    case "rate_limited":
      return {
        kind: "rate_limited",
        minutes: Math.max(1, Math.ceil((error.retryAfter ?? 60) / 60)),
      };
    case "ticket_request_exists":
      return { kind: "exists" };
    case "ticket_webhook_not_configured":
    case "feedback_disabled":
    case "widget_unavailable":
      return { kind: "unavailable" };
    case "validation_error":
      return { kind: "invalid" };
    default:
      return { kind: "failed" };
  }
}

export class AnswerActions {
  private states = new Map<string, AnswerState>();
  private readonly timers = new Set<() => void>();
  private readonly api: WidgetApi;
  private readonly chat: ChatController;
  private readonly host: ChatHost;
  private readonly schedule: Scheduler;

  constructor(
    api: WidgetApi,
    chat: ChatController,
    host: ChatHost,
    schedule: Scheduler = defaultScheduler,
  ) {
    this.api = api;
    this.chat = chat;
    this.host = host;
    this.schedule = schedule;
  }

  state(key: string): AnswerState {
    return this.states.get(key) ?? emptyState();
  }

  private edit(key: string, patch: Partial<AnswerState>): void {
    this.states.set(key, { ...this.state(key), ...patch });
    this.host.changed();
  }

  private fail(error: unknown): ActionError {
    const apiError = asApiError(error);
    this.host.emit("knobridge-error", { code: apiError.code, status: apiError.status });
    return actionError(apiError);
  }

  /** The e-mail field shows only when the signed identity brought no e-mail; the same for name. */
  needs(field: "email" | "name"): boolean {
    return !this.chat.visitor?.[field];
  }

  /** Saves 👍/👎 (an upsert); 👎 without a comment opens the optional comment field. */
  async rate(message: ViewMessage, rating: Rating, comment: string | null = null): Promise<void> {
    const session = this.chat.session;
    if (!session || !message.id || this.state(message.key).feedbackBusy) return;
    this.edit(message.key, { feedbackBusy: true, feedbackError: null });
    try {
      message.feedback = await this.api.rate(session.id, session.token, message.id, {
        rating,
        comment,
      });
      this.host.emit("knobridge-feedback", { messageId: message.id, rating });
      this.edit(message.key, {
        commentOpen: rating === "down" && comment === null,
        commentSent: comment !== null,
      });
    } catch (error) {
      this.edit(message.key, { feedbackError: this.fail(error) });
    } finally {
      this.edit(message.key, { feedbackBusy: false });
    }
  }

  setComment(key: string, comment: string): void {
    this.edit(key, { comment });
  }

  /** Sends the 👎 comment; an empty one just closes the field. */
  async sendComment(message: ViewMessage): Promise<void> {
    const comment = this.state(message.key).comment.trim();
    if (!comment) {
      this.edit(message.key, { commentOpen: false });
      return;
    }
    await this.rate(message, "down", comment);
  }

  /** Opens the form with the summary filled with the question, which the visitor may edit. */
  openTicket(message: ViewMessage): void {
    this.edit(message.key, {
      ticketOpen: true,
      ticketError: null,
      invalid: [],
      draft: { ...this.state(message.key).draft, summary: message.question ?? "" },
    });
  }

  closeTicket(key: string): void {
    this.edit(key, { ticketOpen: false, ticketError: null, invalid: [] });
  }

  setTicketField(key: string, field: TicketField, value: string): void {
    const state = this.state(key);
    this.edit(key, { draft: { ...state.draft, [field]: value } });
  }

  private check(draft: TicketDraft): TicketField[] {
    const invalid: TicketField[] = [];
    const summary = draft.summary.trim();
    if (!summary || summary.length > SUMMARY_MAX_CHARS) invalid.push("summary");
    const email = draft.email.trim();
    if (this.needs("email") && (email.length > EMAIL_MAX_CHARS || !EMAIL.test(email))) {
      invalid.push("email");
    }
    if (this.needs("name") && draft.name.trim().length > NAME_MAX_CHARS) invalid.push("name");
    return invalid;
  }

  /** Asks for the ticket; returns the invalid fields, so the element can focus the first one. */
  async submitTicket(message: ViewMessage): Promise<TicketField[]> {
    const session = this.chat.session;
    const state = this.state(message.key);
    if (!session || !message.id || state.ticketBusy) return [];
    const invalid = this.check(state.draft);
    if (invalid.length) {
      this.edit(message.key, { invalid, ticketError: null });
      return invalid;
    }
    const name = state.draft.name.trim();
    this.edit(message.key, { ticketBusy: true, ticketError: null, invalid: [] });
    try {
      const request = await this.api.requestTicket(session.id, session.token, {
        message_id: message.id,
        summary: state.draft.summary.trim(),
        email: this.needs("email") ? state.draft.email.trim() : null,
        name: this.needs("name") && name ? name : null,
      });
      message.ticketRequest = request;
      this.host.emit("knobridge-ticket-requested", {
        ticketRequestId: request.id,
        messageId: message.id,
      });
      this.edit(message.key, { ticketOpen: false });
      this.poll(message, session, POLL_ATTEMPTS);
    } catch (error) {
      const failure = this.fail(error);
      // The product lost its webhook: the button goes away.
      if (failure.kind === "unavailable") this.chat.ticketEnabled = false;
      // Nothing to fix in the form when there is no ticket to open or one already exists.
      const final = failure.kind === "unavailable" || failure.kind === "exists";
      this.edit(message.key, { ticketError: failure, ticketOpen: !final });
    } finally {
      this.edit(message.key, { ticketBusy: false });
    }
    return [];
  }

  /** Reads the request until it leaves `pending`, while the conversation is still the same. */
  private poll(message: ViewMessage, session: Session, attempts: number): void {
    const request = message.ticketRequest;
    if (request?.status !== "pending" || attempts === 0) return;
    const cancel = this.schedule(() => {
      this.timers.delete(cancel);
      if (this.chat.session !== session) return;
      void this.api
        .ticketRequest(session.id, session.token, request.id)
        .then((latest) => {
          message.ticketRequest = latest;
          this.host.changed();
        })
        .catch(() => {
          // A failed read keeps the last known status; the next attempt may succeed.
        })
        .finally(() => {
          this.poll(message, session, attempts - 1);
        });
    }, POLL_INTERVAL_MS);
    this.timers.add(cancel);
  }

  /** "Nova conversa" or the element left the page: forms closed and polling stopped. */
  reset(): void {
    for (const cancel of this.timers) cancel();
    this.timers.clear();
    this.states = new Map();
  }
}
