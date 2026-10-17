import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { WidgetApi } from "../api/client.ts";
import { ConversationStore, resetMemoryStorage } from "../lib/storage.ts";
import {
  answer,
  API,
  apiError,
  controlledSse,
  ANA,
  created,
  detail,
  IDENTITY,
  identityOf,
  message,
  installFetch,
  KEY,
  TOKEN,
} from "../test/fake-api.ts";
import { ChatController } from "./controller.ts";

const NOW = new Date("2026-10-14T12:00:00Z");

function setup(identity: () => string | null = () => null) {
  const host = { emit: vi.fn(), changed: vi.fn() };
  const store = new ConversationStore("none", KEY);
  const controller = new ChatController(new WidgetApi(API, KEY), store, host, identity, () => NOW);
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
    const { controller, store } = setup(() => IDENTITY);

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

  it("test_controller_step_marks_the_answer_as_searching_until_the_text", async () => {
    const sse = controlledSse();
    installFetch({
      "POST /conversations": created(),
      "POST /conversations/c1/messages": () => sse.response,
    });
    const { controller } = setup();
    const running = controller.send("Como fecho o caixa?");
    await vi.waitFor(() => {
      expect(controller.messages).toHaveLength(2);
    });

    sse.push("step", { message_id: "a1", step: 2, max_steps: 2, query: null });
    await vi.waitFor(() => {
      expect(controller.messages[1]?.searching).toBe(true);
    });
    sse.push("citations", { message_id: "a1", user_message_id: "q1", citations: [] });
    sse.push("delta", { text: "Abra o caixa." });
    sse.push("done", { message_id: "a1", status: "completed", ticket_requests_enabled: false });
    sse.close();
    await running;

    expect(controller.messages[1]?.content).toBe("Abra o caixa.");
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

  it("test_controller_sends_the_identity_as_given_and_keeps_the_verified_visitor", async () => {
    const { calls } = installFetch({
      "POST /conversations": created("c1", TOKEN, ANA),
      "POST /conversations/c1/messages": answer(["Ok."]),
    });
    const { controller } = setup(() => IDENTITY);

    await controller.send("Oi");

    expect(calls[0]?.init.body).toBe(JSON.stringify({ identity: IDENTITY }));
    expect(controller.visitor).toEqual(ANA);
    expect(controller.ticketEnabled).toBe(true);
    expect(controller.session).toEqual({ id: "c1", token: TOKEN });
  });

  it("test_controller_identity_with_the_same_sub_keeps_the_conversation", async () => {
    installFetch({
      "POST /conversations": created(),
      "POST /conversations/c1/messages": answer(["Ok."]),
    });
    let identity = identityOf({ sub: "cliente-42", iat: 1 });
    const { controller } = setup(() => identity);
    await controller.send("Oi");

    identity = identityOf({ sub: "cliente-42", iat: 2 });
    await controller.identityChanged();

    expect(controller.messages).toHaveLength(2);
    expect(controller.session?.id).toBe("c1");
  });

  it("test_controller_identity_of_another_sub_puts_the_conversation_away", async () => {
    const { calls } = installFetch({
      "POST /conversations": [created("c1", TOKEN, ANA), created("c2")],
      "POST /conversations/c1/messages": answer(["Ok."]),
      "POST /conversations/c2/messages": answer(["Outra."]),
    });
    let identity: string | null = IDENTITY;
    const { controller, store } = setup(() => identity);
    await controller.send("Oi");

    identity = null;
    await controller.identityChanged();

    expect(controller.messages).toEqual([]);
    expect(controller.session).toBeNull();
    expect(controller.visitor).toBeNull();
    // The pointer of cliente-42 stays, but an anonymous visitor never reopens it.
    expect(store.load()?.identity_sub).toBe("cliente-42");
    expect(calls).toHaveLength(2);

    await controller.send("De novo");

    expect(calls[2]?.init.body).toBe("{}");
    expect(store.load()).toMatchObject({ conversation_id: "c2", identity_sub: null });
  });

  it("test_controller_identity_change_reopens_the_conversation_of_the_new_visitor", async () => {
    installFetch({
      "GET /conversations/c1": detail([message({ id: "q1", content: "Antes" })], "c1", ANA),
    });
    let identity: string | null = null;
    const { controller, store } = setup(() => identity);
    store.save({
      conversation_id: "c1",
      visitor_token: TOKEN,
      identity_sub: "cliente-42",
      saved_at: NOW.toISOString(),
    });
    await controller.restore();
    expect(controller.messages).toEqual([]);

    identity = IDENTITY;
    await controller.identityChanged();

    expect(controller.messages.map((m) => m.content)).toEqual(["Antes"]);
    expect(controller.visitor).toEqual(ANA);
  });

  it("test_controller_history_arriving_after_an_identity_change_is_dropped", async () => {
    let release!: (response: Response) => void;
    installFetch({
      "GET /conversations/c1": () =>
        new Promise<Response>((resolve) => {
          release = resolve;
        }),
    });
    let identity: string | null = null;
    const { controller, store } = setup(() => identity);
    store.save({
      conversation_id: "c1",
      visitor_token: TOKEN,
      identity_sub: null,
      saved_at: NOW.toISOString(),
    });
    const restoring = controller.restore();
    await vi.waitFor(() => {
      expect(release).toBeTypeOf("function");
    });

    identity = IDENTITY;
    await controller.identityChanged();
    release(detail([message({ id: "q1", content: "De outra pessoa" })]));
    await restoring;

    expect(controller.messages).toEqual([]);
    expect(controller.session).toBeNull();
  });

  it("test_controller_abort_without_answer_does_nothing", () => {
    const { controller, host } = setup();

    controller.abort();

    expect(host.changed).not.toHaveBeenCalled();
  });
});
