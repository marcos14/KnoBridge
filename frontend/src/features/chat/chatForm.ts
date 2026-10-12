import type { TFunction } from "i18next";
import { z } from "zod";

import type { PendingAnswer } from "@/lib/api/chatStream";
import type { Message } from "@/lib/api/conversations";

/** Limits of the contract (`MessageCreate.content`, `FeedbackIn.comment`). */
export const QUESTION_MAX_LENGTH = 8000;
export const FEEDBACK_COMMENT_MAX_LENGTH = 2000;

/** How close to the end (in pixels) still counts as "at the end" for following the answer. */
export const SCROLL_END_TOLERANCE = 48;

export function questionSchema(t: TFunction) {
  return z.object({
    content: z
      .string()
      .trim()
      .min(1, t("chat.composer.required"))
      .max(QUESTION_MAX_LENGTH, t("chat.composer.tooLong", { max: QUESTION_MAX_LENGTH })),
  });
}

export type QuestionValues = z.infer<ReturnType<typeof questionSchema>>;

export function feedbackCommentSchema(t: TFunction) {
  return z.object({
    comment: z
      .string()
      .trim()
      .max(
        FEEDBACK_COMMENT_MAX_LENGTH,
        t("chat.feedback.commentTooLong", { max: FEEDBACK_COMMENT_MAX_LENGTH }),
      ),
  });
}

export type FeedbackCommentValues = z.infer<ReturnType<typeof feedbackCommentSchema>>;

/** Whether a scrolled box shows its end, so new content should keep it there. */
export function isAtEnd(box: { scrollHeight: number; scrollTop: number; clientHeight: number }) {
  return box.scrollHeight - box.scrollTop - box.clientHeight <= SCROLL_END_TOLERANCE;
}

/** The question an assistant answer replied to: the user message right before it, if any. */
export function questionBefore(messages: readonly Message[], answerId: string): string | null {
  const position = messages.findIndex((message) => message.id === answerId);
  for (let index = position - 1; index >= 0; index--) {
    const message = messages[index];
    if (message?.role === "user") {
      return message.content;
    }
  }
  return null;
}

/**
 * Saved messages not already on screen as the exchange being streamed. Once the `citations` event
 * names them, the saved question and answer are hidden by id. Before it, a reload (the new
 * conversation opening) can already bring them, since the server saves both before streaming: a
 * tail made of that question, alone or followed by a `streaming` answer, is the same exchange.
 */
export function visibleMessages(
  messages: readonly Message[],
  pending: Pick<PendingAnswer, "question" | "userMessageId" | "messageId"> | null,
): readonly Message[] {
  if (pending === null) {
    return messages;
  }
  if (pending.userMessageId !== null) {
    return messages.filter(
      (message) => message.id !== pending.messageId && message.id !== pending.userMessageId,
    );
  }
  const last = messages.at(-1);
  const tail = last?.role === "assistant" && last.status === "streaming" ? 2 : 1;
  const question = messages.at(-tail);
  return question?.role === "user" && question.content === pending.question
    ? messages.slice(0, -tail)
    : messages;
}

/** Longest summary `POST .../ticket-requests` accepts. */
export const TICKET_SUMMARY_MAX_LENGTH = 2000;

export function ticketSummarySchema(t: TFunction) {
  return z.object({
    summary: z
      .string()
      .trim()
      .min(1, t("chat.ticket.summaryRequired"))
      .max(
        TICKET_SUMMARY_MAX_LENGTH,
        t("chat.ticket.summaryTooLong", { max: TICKET_SUMMARY_MAX_LENGTH }),
      ),
  });
}

export type TicketSummaryValues = z.infer<ReturnType<typeof ticketSummarySchema>>;

/** Whether a ticket can still be asked for this answer: finished and without a request. */
export function canRequestTicket(message: Message): boolean {
  return (
    message.role === "assistant" &&
    (message.status === "completed" || message.status === "no_source") &&
    (message.ticket_request ?? null) === null
  );
}

/**
 * The answer "Abrir chamado" of the conversation menu asks a ticket for: the last finished answer
 * when it has no request yet; `null` otherwise.
 */
export function ticketCandidate(messages: readonly Message[]): Message | null {
  const last = messages.findLast((message) => message.role === "assistant");
  return last !== undefined && canRequestTicket(last) ? last : null;
}

/** Whether Enter in the composer sends: plain Enter, not Shift+Enter nor while composing (IME). */
export function isSendKey(event: { key: string; shiftKey: boolean; isComposing: boolean }) {
  return event.key === "Enter" && !event.shiftKey && !event.isComposing;
}
