import { describe, expect, it } from "vitest";

import { i18n } from "@/i18n";
import { makeMessage, makeQuestion, messageId } from "@/test/factories";

import {
  feedbackCommentSchema,
  isAtEnd,
  isSendKey,
  QUESTION_MAX_LENGTH,
  questionBefore,
  questionSchema,
  visibleMessages,
} from "./chatForm";

const t = i18n.t.bind(i18n);

describe("chatForm", () => {
  it("test_question_schema_trims_and_limits_the_question", () => {
    const schema = questionSchema(t);

    expect(schema.parse({ content: "  Oi  " })).toEqual({ content: "Oi" });
    expect(schema.safeParse({ content: "   " }).error?.issues[0]?.message).toBe(
      "Escreva uma pergunta.",
    );
    expect(
      schema.safeParse({ content: "a".repeat(QUESTION_MAX_LENGTH + 1) }).error?.issues[0]?.message,
    ).toBe("A pergunta pode ter até 8000 caracteres.");
  });

  it("test_feedback_comment_schema_allows_empty_and_limits_length", () => {
    const schema = feedbackCommentSchema(t);

    expect(schema.parse({ comment: "" })).toEqual({ comment: "" });
    expect(schema.safeParse({ comment: "a".repeat(2001) }).success).toBe(false);
  });

  it("test_is_at_end_tolerates_a_few_pixels", () => {
    expect(isAtEnd({ scrollHeight: 1000, scrollTop: 560, clientHeight: 400 })).toBe(true);
    expect(isAtEnd({ scrollHeight: 1000, scrollTop: 400, clientHeight: 400 })).toBe(false);
  });

  it("test_question_before_finds_the_previous_user_message", () => {
    const messages = [
      makeQuestion("Primeira", messageId(1)),
      makeMessage({ id: messageId(2) }),
      makeMessage({ id: messageId(3) }),
    ];

    expect(questionBefore(messages, messageId(3))).toBe("Primeira");
    expect(questionBefore(messages, messageId(1))).toBeNull();
    expect(questionBefore(messages, "missing")).toBeNull();
  });

  describe("visibleMessages", () => {
    const earlier = [makeQuestion("Antes", messageId(1)), makeMessage({ id: messageId(2) })];
    const question = makeQuestion("Como fecho o caixa?", messageId(3));
    const answer = makeMessage({ id: messageId(4), content: "", status: "streaming" });
    const waiting = { question: "Como fecho o caixa?", userMessageId: null, messageId: null };

    it("test_visible_messages_without_pending_keeps_everything", () => {
      expect(visibleMessages([...earlier, question], null)).toEqual([...earlier, question]);
    });

    it("test_visible_messages_hides_the_pending_exchange_by_id", () => {
      const named = { ...waiting, userMessageId: messageId(3), messageId: messageId(4) };

      expect(visibleMessages([...earlier, question, answer], named)).toEqual(earlier);
    });

    it("test_visible_messages_hides_the_saved_tail_before_ids_arrive", () => {
      expect(visibleMessages([...earlier, question, answer], waiting)).toEqual(earlier);
      expect(visibleMessages([...earlier, question], waiting)).toEqual(earlier);
    });

    it("test_visible_messages_keeps_a_finished_answer_to_the_same_question", () => {
      // Resending a failed answer asks the same question again.
      const failed = makeMessage({ id: messageId(4), status: "failed" });

      expect(visibleMessages([...earlier, question, failed], waiting)).toEqual([
        ...earlier,
        question,
        failed,
      ]);
      expect(visibleMessages([], waiting)).toEqual([]);
    });
  });

  it("test_is_send_key_is_plain_enter", () => {
    expect(isSendKey({ key: "Enter", shiftKey: false, isComposing: false })).toBe(true);
    expect(isSendKey({ key: "Enter", shiftKey: true, isComposing: false })).toBe(false);
    expect(isSendKey({ key: "Enter", shiftKey: false, isComposing: true })).toBe(false);
    expect(isSendKey({ key: "a", shiftKey: false, isComposing: false })).toBe(false);
  });
});
