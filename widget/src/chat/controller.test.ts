import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { WidgetApi } from "../api/client.ts";
import { ConversationStore, resetMemoryStorage } from "../lib/storage.ts";
import {
  answer,
  API,
  apiError,
  controlledSse,
  created,
  installFetch,
  KEY,
  TOKEN,
} from "../test/fake-api.ts";
import { ChatController } from "./controller.ts";

const NOW = new Date("2026-10-14T12:00:00Z");

function setup(sub: string | null = null) {
  const host = { emit: vi.fn(), changed: vi.fn() };
  const store = new ConversationStore("none", KEY);
  const controller = new ChatController(
    new WidgetApi(API, KEY),
    store,
    host,
    () => sub,
    () => NOW,
  );
  return { controller, host, store };
}

beforeEach(() => {
  resetMemoryStorage();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("ChatController", () => {
  it("test_controller_saves_the_pointer_with_the_identity_sub_and_clock", async () => {
    installFetch({
      "POST /conversations": created(),
      "POST /conversations/c1/messages": answer(["Ok."]),
    });
    const { controller, store } = setup("cliente-42");

    await controller.send("Oi");

    expect(store.load()).toEqual({
      conversation_id: "c1",
      visitor_token: TOKEN,
      identity_sub: "cliente-42",
      saved_at: "2026-10-14T12:00:00.000Z",
    });
    expect(controller.messages.map((m) => [m.role, m.content, m.status])).toEqual([
      ["user", "Oi", "completed"],
      ["assistant", "Ok.", "completed"],
    ]);
  });

  it("test_controller_retry_ignores_unknown_or_busy", async () => {
    const sse = controlledSse();
    const { calls } = installFetch({
      "POST /conversations": created(),
      "POST /conversations/c1/messages": [apiError(500, "chat_failed"), () => sse.response],
    });
    const { controller } = setup();
    await controller.send("Oi");
    const failed = controller.messages[1];

    await controller.retry("nope");
    const running = controller.retry(failed?.key ?? "");
    await vi.waitFor(() => {
      expect(calls).toHaveLength(3);
    });
    await controller.retry(controller.messages[1]?.key ?? "");

    expect(controller.messages).toHaveLength(2);
    sse.push("citations", { message_id: "a1", user_message_id: "q1", citations: [] });
    sse.push("done", { message_id: "a1", status: "completed", ticket_requests_enabled: false });
    sse.close();
    await running;
    expect(controller.messages[1]?.status).toBe("completed");
  });

  it("test_controller_send_while_busy_is_ignored", async () => {
    const { calls } = installFetch({
      "POST /conversations": created(),
      "POST /conversations/c1/messages": answer(["Ok."]),
    });
    const { controller } = setup();

    const first = controller.send("Um");
    await controller.send("Dois");
    await first;

    expect(calls).toHaveLength(2);
    expect(controller.messages).toHaveLength(2);
  });

  it("test_controller_abort_without_answer_does_nothing", () => {
    const { controller, host } = setup();

    controller.abort();

    expect(host.changed).not.toHaveBeenCalled();
  });
});
