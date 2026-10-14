// Templates under a finished answer (docs/specs/widget.md, "Comportamento" and "Acessibilidade"):
// 👍/👎 with aria-pressed and the optional comment on 👎, the "Abrir chamado" button and form
// (errors tied by aria-describedby) and the state of the request. State and calls: ../chat/actions.ts.

import { html, nothing, type TemplateResult } from "lit";

import type { Rating, TicketRequest } from "../api/types.ts";
import {
  COMMENT_MAX_CHARS,
  NAME_MAX_CHARS,
  SUMMARY_MAX_CHARS,
  type ActionError,
  type AnswerActions,
  type AnswerState,
  type TicketField,
} from "../chat/actions.ts";
import type { ViewMessage } from "../chat/controller.ts";
import type { MessageKey, Translate } from "../i18n/index.ts";
import { isHttpUrl } from "../lib/markdown.ts";

export interface ActionsContext {
  t: Translate;
  actions: AnswerActions;
  feedbackEnabled: boolean;
  ticketEnabled: boolean;
  /** Moves the focus to an element of the shadow root, by id, after the next render. */
  focus(id: string): void;
}

export function fieldId(messageKey: string, field: TicketField): string {
  return `ticket-${messageKey}-${field}`;
}

function errorText(error: ActionError, t: Translate, failed: MessageKey): string {
  switch (error.kind) {
    case "rate_limited":
      return error.minutes === 1
        ? t("rateLimitedOne")
        : t("rateLimited", { minutes: error.minutes });
    case "exists":
      return t("ticketExists");
    case "invalid":
      return t("ticketInvalid");
    case "unavailable":
      return t(failed === "feedbackFailed" ? "feedbackUnavailable" : "ticketUnavailable");
    case "failed":
      return t(failed);
  }
}

function renderRating(message: ViewMessage, state: AnswerState, ctx: ActionsContext) {
  const current = message.feedback?.rating ?? null;
  const button = (rating: Rating, label: MessageKey, icon: string) =>
    html`<button
      type="button"
      class="rate"
      aria-label=${ctx.t(label)}
      aria-pressed=${current === rating ? "true" : "false"}
      ?disabled=${state.feedbackBusy}
      @click=${() => {
        void ctx.actions.rate(message, rating);
      }}
    >
      ${icon}
    </button>`;
  return [button("up", "rateUp", "👍"), button("down", "rateDown", "👎")];
}

function renderComment(message: ViewMessage, state: AnswerState, ctx: ActionsContext) {
  const id = `comment-${message.key}`;
  return html`<form
    class="inline-form"
    @submit=${(event: Event) => {
      event.preventDefault();
      void ctx.actions.sendComment(message);
    }}
  >
    <label for=${id}>${ctx.t("commentLabel")}</label>
    <textarea
      id=${id}
      rows="2"
      maxlength=${COMMENT_MAX_CHARS}
      .value=${state.comment}
      @input=${(event: Event) => {
        ctx.actions.setComment(message.key, (event.target as HTMLTextAreaElement).value);
      }}
    ></textarea>
    <button type="submit" ?disabled=${state.feedbackBusy}>${ctx.t("commentSend")}</button>
  </form>`;
}

function renderField(
  message: ViewMessage,
  state: AnswerState,
  ctx: ActionsContext,
  field: TicketField,
  label: string,
  error: string,
): TemplateResult {
  const id = fieldId(message.key, field);
  const invalid = state.invalid.includes(field);
  const onInput = (event: Event) => {
    const target = event.target as HTMLInputElement | HTMLTextAreaElement;
    ctx.actions.setTicketField(message.key, field, target.value);
  };
  const control =
    field === "summary"
      ? html`<textarea
          id=${id}
          rows="3"
          .value=${state.draft.summary}
          aria-invalid=${invalid ? "true" : "false"}
          aria-describedby=${invalid ? `${id}-error` : nothing}
          @input=${onInput}
        ></textarea>`
      : html`<input
          id=${id}
          type=${field === "email" ? "email" : "text"}
          autocomplete=${field}
          .value=${state.draft[field]}
          aria-invalid=${invalid ? "true" : "false"}
          aria-describedby=${invalid ? `${id}-error` : nothing}
          @input=${onInput}
        />`;
  return html`<label for=${id}>${label}</label> ${control}
    ${invalid ? html`<span class="field-error" id=${`${id}-error`}>${error}</span>` : nothing}`;
}

function renderTicketForm(message: ViewMessage, state: AnswerState, ctx: ActionsContext) {
  const { t, actions } = ctx;
  const submit = async (event: Event) => {
    event.preventDefault();
    const [first] = await actions.submitTicket(message);
    if (first) ctx.focus(fieldId(message.key, first));
  };
  return html`<form part="ticket-form" class="inline-form" novalidate @submit=${submit}>
    <p>${t("ticketIntro")}</p>
    ${renderField(message, state, ctx, "summary", t("ticketSummary"), t("summaryInvalid", { max: SUMMARY_MAX_CHARS }))}
    ${actions.needs("email") ? renderField(message, state, ctx, "email", t("ticketEmail"), t("emailInvalid")) : nothing}
    ${actions.needs("name") ? renderField(message, state, ctx, "name", t("ticketName"), t("nameInvalid", { max: NAME_MAX_CHARS })) : nothing}
    <div class="form-buttons">
      <button type="submit" ?disabled=${state.ticketBusy}>${t("ticketSubmit")}</button>
      <button
        type="button"
        @click=${() => {
          actions.closeTicket(message.key);
        }}
      >
        ${t("ticketCancel")}
      </button>
    </div>
  </form>`;
}

function renderTicketStatus(request: TicketRequest, t: Translate): TemplateResult {
  if (request.status === "failed") {
    return html`<p class="notice" role="status">${t("ticketDeliveryFailed")}</p>`;
  }
  if (request.status === "pending") {
    return html`<p class="notice" role="status">${t("ticketRequested")}</p>`;
  }
  const number = request.external_ticket_id;
  return html`<p class="notice" role="status">
    ${number ? t("ticketDelivered", { number }) : t("ticketDeliveredNoNumber")}
    ${
      isHttpUrl(request.external_url)
        ? html`<a href=${request.external_url} target="_blank" rel="noopener noreferrer"
            >${t("ticketLink")}</a
          >`
        : nothing
    }
  </p>`;
}

/** Feedback and "Abrir chamado" under an answer that finished with `completed` or `no_source`. */
export function renderAnswerActions(
  message: ViewMessage,
  ctx: ActionsContext,
): TemplateResult | typeof nothing {
  if (!message.id || (message.status !== "completed" && message.status !== "no_source")) {
    return nothing;
  }
  const { t, actions } = ctx;
  const state = actions.state(message.key);
  const ticketButton =
    ctx.ticketEnabled &&
    !message.ticketRequest &&
    !state.ticketOpen &&
    state.ticketError?.kind !== "exists";
  // With no source the ticket is the way forward, so its button stands out.
  const ticketClass = message.status === "no_source" ? "ticket primary" : "ticket";
  return html`<div class="answer-actions">
    <div class="action-row" role="group" aria-label=${t("answerActions")}>
      ${ctx.feedbackEnabled ? renderRating(message, state, ctx) : nothing}
      ${
        ticketButton
          ? html`<button
              type="button"
              class=${ticketClass}
              @click=${() => {
                actions.openTicket(message);
                ctx.focus(fieldId(message.key, "summary"));
              }}
            >
              ${t("ticketOpen")}
            </button>`
          : nothing
      }
    </div>
    ${state.commentOpen ? renderComment(message, state, ctx) : nothing}
    ${state.commentSent ? html`<p class="notice" role="status">${t("commentThanks")}</p>` : nothing}
    ${
      state.feedbackError
        ? html`<p class="notice" role="alert">
            ${errorText(state.feedbackError, t, "feedbackFailed")}
          </p>`
        : nothing
    }
    ${state.ticketOpen ? renderTicketForm(message, state, ctx) : nothing}
    ${message.ticketRequest ? renderTicketStatus(message.ticketRequest, t) : nothing}
    ${
      state.ticketError
        ? html`<p class="notice" role="alert">
            ${errorText(state.ticketError, t, "ticketFailed")}
          </p>`
        : nothing
    }
  </div>`;
}
