import type { TFunction } from "i18next";
import { z } from "zod";

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

/** Whether a source URI can be opened as a web link (other URIs, such as file paths, are shown). */
export function isWebUri(uri: string): boolean {
  return /^https?:\/\//i.test(uri);
}

/** Whether Enter in the composer sends: plain Enter, not Shift+Enter nor while composing (IME). */
export function isSendKey(event: { key: string; shiftKey: boolean; isComposing: boolean }) {
  return event.key === "Enter" && !event.shiftKey && !event.isComposing;
}
