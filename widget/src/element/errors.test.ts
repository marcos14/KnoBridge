import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import "../index.ts";
import { resetMemoryStorage } from "../lib/storage.ts";
import { ask, find, form, mount, root, settle, text } from "../test/dom.ts";
import {
  answer,
  apiError,
  CONFIG,
  controlledSse,
  created,
  installFetch,
  json,
  KEY,
  OTHER_TOKEN,
} from "../test/fake-api.ts";

beforeEach(() => {
  localStorage.clear();
  resetMemoryStorage();
});

afterEach(() => {
  document.body.replaceChildren();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("<knobridge-chat> errors", () => {
  it.each([
    ["125", "Tente de novo em 3 minutos."],
    ["60", "Tente de novo em 1 minuto."],
  ])("test_rate_limited_with_retry_after_%s_says_when_to_try_again", async (after, expected) => {
    installFetch({
      "GET /config": json(CONFIG),
      "POST /conversations": created(),
      "POST /conversations/c1/messages": apiError(429, "rate_limited", { "Retry-After": after }),
    });
    const { el, events } = await mount({ mode: "inline" });

    await ask(el, "Oi");
    await settle(el);

    expect(text(el)).toContain(`Muitas mensagens em pouco tempo. ${expected}`);
    expect(root(el).querySelector(".retry")).toBeNull();
    expect(events.at(-1)).toEqual({
      name: "knobridge-error",
      detail: { code: "rate_limited", status: 429 },
    });
  });

  it("test_rate_limited_without_retry_after_waits_a_minute", async () => {
    installFetch({
      "GET /config": json(CONFIG),
      "POST /conversations": apiError(429, "rate_limited"),
    });
    const { el } = await mount({ mode: "inline" });

    await ask(el, "Oi");
    await settle(el);

    expect(text(el)).toContain("Tente de novo em 1 minuto.");
  });

  it("test_network_failure_offers_try_again_which_resends", async () => {
    const { calls } = installFetch({
      "GET /config": json(CONFIG),
      "POST /conversations": created(),
      "POST /conversations/c1/messages": [new TypeError("offline"), answer(["Agora foi."])],
    });
    const { el, events } = await mount({ mode: "inline" });

    await ask(el, "Oi");
    await settle(el);
    expect(text(el)).toContain("Não consegui responder agora. Tente de novo.");
    expect(events.at(-1)?.detail).toEqual({ code: "network_error", status: null });

    find(el, ".retry").click();
    await settle(el);

    expect(text(el)).toContain("Agora foi.");
    expect(text(el)).not.toContain("Não consegui");
    expect(root(el).querySelectorAll(".message.user")).toHaveLength(1);
    expect(calls.filter((call) => call.path === "/conversations")).toHaveLength(1);
  });

  it("test_error_event_in_the_stream_fails_the_answer", async () => {
    const sse = controlledSse();
    installFetch({
      "GET /config": json(CONFIG),
      "POST /conversations": created(),
      "POST /conversations/c1/messages": () => sse.response,
    });
    const { el, events } = await mount({ mode: "inline" });
    await ask(el, "Oi");
    sse.push("citations", { message_id: "a1", user_message_id: "q1", citations: [] });
    sse.push("delta", { text: "Parcial" });
    sse.push("error", {
      message_id: "a1",
      status: "failed",
      error: { code: "provider_unavailable", message: "x", details: null },
    });
    await settle(el);

    expect(text(el)).toContain("Parcial");
    expect(text(el)).toContain("Não consegui responder agora.");
    expect(text(el)).not.toContain("provider_unavailable");
    expect(events.slice(-2)).toEqual([
      { name: "knobridge-error", detail: { code: "provider_unavailable", status: null } },
      {
        name: "knobridge-answer",
        detail: { conversationId: "c1", messageId: "a1", status: "failed", citations: 0 },
      },
    ]);
  });

  it("test_stream_cut_after_citations_reports_the_failed_answer", async () => {
    const sse = controlledSse();
    installFetch({
      "GET /config": json(CONFIG),
      "POST /conversations": created(),
      "POST /conversations/c1/messages": () => sse.response,
    });
    const { el, events } = await mount({ mode: "inline" });
    await ask(el, "Oi");
    sse.push("citations", { message_id: "a1", user_message_id: "q1", citations: [] });
    await vi.waitFor(() => {
      expect(events.at(-1)?.name).toBe("knobridge-message-sent");
    });
    sse.fail();
    await settle(el);

    expect(events.at(-1)).toEqual({
      name: "knobridge-answer",
      detail: { conversationId: "c1", messageId: "a1", status: "failed", citations: 0 },
    });
  });

  it("test_api_error_on_create_reports_its_code", async () => {
    installFetch({
      "GET /config": json(CONFIG),
      "POST /conversations": apiError(409, "level_not_configured"),
    });
    const { el, events } = await mount({ mode: "inline" });

    await ask(el, "Oi");
    await settle(el);

    expect(text(el)).toContain("Não consegui responder agora.");
    expect(events.at(-1)).toEqual({
      name: "knobridge-error",
      detail: { code: "level_not_configured", status: 409 },
    });
  });

  it("test_widget_unavailable_while_chatting_says_so", async () => {
    installFetch({
      "GET /config": json(CONFIG),
      "POST /conversations": created(),
      "POST /conversations/c1/messages": apiError(404, "widget_unavailable"),
    });
    const { el } = await mount({ mode: "inline" });

    await ask(el, "Oi");
    await settle(el);

    expect(text(el)).toContain("Chat indisponível no momento.");
    expect(localStorage.getItem(`knobridge:v1:${KEY}`)).not.toBeNull();
  });

  it("test_lost_conversation_starts_a_new_one_on_retry", async () => {
    const { calls } = installFetch({
      "GET /config": json(CONFIG),
      "POST /conversations": [created("c1"), created("c2", OTHER_TOKEN)],
      "POST /conversations/c1/messages": apiError(401, "invalid_visitor_token"),
      "POST /conversations/c2/messages": answer(["Nova."]),
    });
    const { el } = await mount({ mode: "inline" });

    await ask(el, "Oi");
    await settle(el);
    expect(localStorage.getItem(`knobridge:v1:${KEY}`)).toBeNull();
    find(el, ".retry").click();
    await settle(el);

    expect(text(el)).toContain("Nova.");
    expect(calls.filter((call) => call.path === "/conversations")).toHaveLength(2);
  });
});

describe("<knobridge-chat> interruptions", () => {
  it("test_removing_the_element_interrupts_the_answer", async () => {
    const sse = controlledSse();
    const { calls } = installFetch({
      "GET /config": json(CONFIG),
      "POST /conversations": created(),
      "POST /conversations/c1/messages": (init) => {
        init.signal?.addEventListener("abort", () => {
          sse.fail(new DOMException("aborted", "AbortError"));
        });
        return sse.response;
      },
    });
    const { el } = await mount({ mode: "inline" });
    await ask(el, "Oi");
    sse.push("citations", { message_id: "a1", user_message_id: "q1", citations: [] });
    sse.push("delta", { text: "Começo" });
    await vi.waitFor(() => {
      expect(text(el)).toContain("Começo");
    });

    el.remove();
    document.body.append(el);
    await settle(el);

    expect(text(el)).toContain("A resposta foi interrompida.");
    expect(calls).toHaveLength(3);
  });

  it("test_new_conversation_during_an_answer_stops_it", async () => {
    const sse = controlledSse();
    installFetch({
      "GET /config": json(CONFIG),
      "POST /conversations": created(),
      "POST /conversations/c1/messages": (init) => {
        init.signal?.addEventListener("abort", () => {
          sse.fail(new DOMException("aborted", "AbortError"));
        });
        return sse.response;
      },
    });
    const { el, events } = await mount({ mode: "inline" });
    await ask(el, "Oi");
    await vi.waitFor(() => {
      expect(text(el)).toContain("Digitando…");
    });

    el.newConversation();
    await settle(el);

    expect(root(el).querySelectorAll(".message")).toHaveLength(1);
    expect(localStorage.getItem(`knobridge:v1:${KEY}`)).toBeNull();
    expect(events.some((event) => event.name === "knobridge-error")).toBe(false);
  });

  it("test_a_question_while_busy_is_ignored", async () => {
    const sse = controlledSse();
    const { calls } = installFetch({
      "GET /config": json(CONFIG),
      "POST /conversations": created(),
      "POST /conversations/c1/messages": () => sse.response,
    });
    const { el } = await mount({ mode: "inline" });
    await ask(el, "Primeira");
    await vi.waitFor(() => {
      expect(calls).toHaveLength(3);
    });

    await ask(el, "Segunda");
    form(el).requestSubmit();

    expect(calls).toHaveLength(3);
    expect(text(el)).not.toContain("Você: Segunda");
  });
});
