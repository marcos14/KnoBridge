import { describe, expect, it } from "vitest";

import { ChatProtocolError, parseChatEvent } from "./chatEvents";

const citation = {
  index: 1,
  title: "Manual",
  uri: null,
  snippet: "Trecho.",
  document_id: null,
};

describe("parseChatEvent", () => {
  it("test_parse_chat_event_reads_citations", () => {
    const event = parseChatEvent({
      event: "citations",
      data: JSON.stringify({ message_id: "a", user_message_id: "q", citations: [citation] }),
    });

    expect(event).toEqual({
      type: "citations",
      messageId: "a",
      userMessageId: "q",
      citations: [citation],
    });
  });

  it("test_parse_chat_event_reads_delta_done_and_error", () => {
    expect(parseChatEvent({ event: "delta", data: '{"text":"Oi"}' })).toEqual({
      type: "delta",
      text: "Oi",
    });
    expect(
      parseChatEvent({ event: "done", data: '{"message_id":"a","status":"no_source"}' }),
    ).toEqual({
      type: "done",
      messageId: "a",
      status: "no_source",
      ticketRequestsEnabled: false,
      steps: null,
    });
    expect(
      parseChatEvent({
        event: "error",
        data: '{"message_id":"a","status":"failed","error":{"code":"provider_unavailable"}}',
      }),
    ).toEqual({ type: "error", messageId: "a", code: "provider_unavailable" });
  });

  it("test_parse_chat_event_done_reads_ticket_requests_enabled", () => {
    const data = '{"message_id":"a","status":"no_source","ticket_requests_enabled":true,"steps":3}';

    expect(parseChatEvent({ event: "done", data })).toEqual({
      type: "done",
      messageId: "a",
      status: "no_source",
      ticketRequestsEnabled: true,
      steps: 3,
    });
  });

  it("test_parse_chat_event_reads_step_with_or_without_query", () => {
    expect(
      parseChatEvent({
        event: "step",
        data: '{"message_id":"a","step":2,"max_steps":3,"query":"tabela do caixa"}',
      }),
    ).toEqual({ type: "step", messageId: "a", step: 2, maxSteps: 3, query: "tabela do caixa" });
    expect(
      parseChatEvent({
        event: "step",
        data: '{"message_id":"a","step":2,"max_steps":2,"query":null}',
      }),
    ).toMatchObject({ query: null });
  });

  it("test_parse_chat_event_error_without_code_is_chat_failed", () => {
    expect(parseChatEvent({ event: "error", data: '{"message_id":"a","error":null}' })).toEqual({
      type: "error",
      messageId: "a",
      code: "chat_failed",
    });
    expect(
      parseChatEvent({ event: "error", data: '{"message_id":"a","error":{"code":7}}' }),
    ).toMatchObject({ code: "chat_failed" });
  });

  it("test_parse_chat_event_ignores_unknown_events", () => {
    expect(parseChatEvent({ event: "message", data: "{}" })).toBeNull();
  });

  it.each([
    ["delta", "not json"],
    ["delta", "[1]"],
    ["delta", '{"text":1}'],
    ["citations", '{"message_id":"a","user_message_id":"q"}'],
    ["done", '{"message_id":"a","status":"failed"}'],
    ["step", '{"message_id":"a","step":"2","max_steps":3}'],
  ])("test_parse_chat_event_rejects_malformed_%s", (name, data) => {
    expect(() => parseChatEvent({ event: name, data })).toThrow(ChatProtocolError);
  });
});
