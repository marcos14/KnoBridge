import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import "../index.ts";
import { resetMemoryStorage } from "../lib/storage.ts";
import {
  ask,
  find,
  findByText,
  form,
  mount,
  press,
  root,
  sendButton,
  settle,
  text,
  textarea,
  type,
} from "../test/dom.ts";
import {
  answer,
  apiError,
  citation,
  CONFIG,
  controlledSse,
  created,
  detail,
  installFetch,
  json,
  KEY,
  message,
  TOKEN,
} from "../test/fake-api.ts";

const STORAGE_KEY = `knobridge:v1:${KEY}`;

beforeEach(() => {
  localStorage.clear();
  resetMemoryStorage();
});

afterEach(() => {
  document.body.replaceChildren();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function stored(): unknown {
  return JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "null");
}

describe("<knobridge-chat> streaming", () => {
  it("test_send_streams_the_answer_and_announces_it_at_the_end", async () => {
    const sse = controlledSse();
    const { calls } = installFetch({
      "GET /config": json(CONFIG),
      "POST /conversations": created(),
      "POST /conversations/c1/messages": [() => sse.response, answer(["Segunda."], { id: "a2" })],
    });
    const { el, events } = await mount({ mode: "inline" });

    await ask(el, "  Como fecho o caixa?  ");
    await vi.waitFor(() => {
      expect(text(el)).toContain("Digitando…");
    });
    const log = find(el, "[role=log]");
    const pending = find(el, ".message.assistant[aria-busy=true]");
    expect(log.getAttribute("aria-live")).toBe("polite");
    expect(text(el)).toContain("Você: Como fecho o caixa?");
    expect(textarea(el).readOnly).toBe(true);
    expect(sendButton(el).disabled).toBe(true);

    sse.push("citations", {
      message_id: "a1",
      user_message_id: "q1",
      citations: [citation(1)],
    });
    sse.push("delta", { text: "Abra o **menu** " });
    await vi.waitFor(() => {
      expect(pending.querySelector("strong")?.textContent).toBe("menu");
    });
    expect(pending.getAttribute("aria-busy")).toBe("true");
    sse.push("delta", { text: "Caixa [1]." });
    sse.push("done", { message_id: "a1", status: "completed", ticket_requests_enabled: true });
    sse.close();
    await settle(el);

    expect(pending.getAttribute("aria-busy")).toBe("false");
    expect(text(el)).toContain("Abra o menu Caixa [1].");
    expect(text(el)).not.toContain("Digitando…");
    expect(stored()).toMatchObject({
      conversation_id: "c1",
      visitor_token: TOKEN,
      identity_sub: null,
    });
    expect(events.slice(1)).toEqual([
      { name: "knobridge-message-sent", detail: { conversationId: "c1", messageId: "a1" } },
      {
        name: "knobridge-answer",
        detail: { conversationId: "c1", messageId: "a1", status: "completed", citations: 1 },
      },
    ]);

    await ask(el, "E depois?");
    await settle(el);

    expect(text(el)).toContain("Segunda.");
    expect(calls.filter((call) => call.path === "/conversations")).toHaveLength(1);
  });

  it("test_send_ignores_empty_shift_enter_and_too_long_questions", async () => {
    const { calls } = installFetch({
      "GET /config": json({ ...CONFIG, question_max_chars: 10 }),
    });
    const { el } = await mount({ mode: "inline" });

    await ask(el, "   ");
    const input = await type(el, "linha");
    press(input, "Enter", { shiftKey: true });
    press(input, "Enter", { isComposing: true });
    press(input, "a");
    await type(el, "uma pergunta longa");
    press(input, "Enter");
    form(el).requestSubmit();
    await el.updateComplete;

    expect(calls).toHaveLength(1);
    expect(find(el, "#counter").textContent).toContain("passou do limite de 10 caracteres");
    expect(find(el, "#counter").className).toBe("counter over");
    expect(sendButton(el).disabled).toBe(true);
    await type(el, "curta");
    expect(find(el, "#counter").textContent.trim()).toBe("5 de 10 caracteres");
    expect(find(el, "textarea").getAttribute("aria-describedby")).toBe("counter");
  });

  it("test_answer_text_is_escaped_never_html", async () => {
    installFetch({
      "GET /config": json(CONFIG),
      "POST /conversations": created(),
      "POST /conversations/c1/messages": answer([
        '<img src=x onerror="alert(1)"> [link](javascript:x)',
      ]),
    });
    const { el } = await mount({ mode: "inline" });

    await ask(el, "<b>oi</b>");
    await settle(el);

    expect(root(el).querySelector("img, b, a")).toBeNull();
    expect(text(el)).toContain('<img src=x onerror="alert(1)">');
    expect(text(el)).toContain("<b>oi</b>");
  });

  it("test_no_source_answer_shows_the_product_message", async () => {
    installFetch({
      "GET /config": json(CONFIG),
      "POST /conversations": created(),
      "POST /conversations/c1/messages": answer(["Não encontrei essa informação."], {
        status: "no_source",
      }),
    });
    const { el, events } = await mount({ mode: "inline" });

    await ask(el, "Qual a cor do céu?");
    await settle(el);

    expect(text(el)).toContain("Não encontrei essa informação.");
    expect(root(el).querySelector("[part=citations]")).toBeNull();
    expect(events.at(-1)?.detail).toMatchObject({ status: "no_source", citations: 0 });
  });
});

describe("<knobridge-chat> citations", () => {
  it("test_citation_marker_opens_the_source_and_moves_focus", async () => {
    installFetch({
      "GET /config": json(CONFIG),
      "POST /conversations": created(),
      "POST /conversations/c1/messages": answer(["Veja [1] e [2]."], {
        citations: [citation(1, { url: "https://erp.example.com/doc" }), citation(2)],
      }),
    });
    const { el } = await mount({ mode: "inline" });
    await ask(el, "Como?");
    await settle(el);

    const marker = find(el, "button.cite");
    expect(marker.getAttribute("aria-label")).toBe("Fonte 1: manual/caixa-1.md");
    marker.click();
    await el.updateComplete;
    await el.updateComplete;

    const toggle = findByText(el, "[part=citations] button", "[1]");
    const detailOne = find(el, `#${toggle.id}-detail`);
    expect(toggle.getAttribute("aria-expanded")).toBe("true");
    expect(root(el).activeElement).toBe(toggle);
    expect(detailOne.hidden).toBe(false);
    expect(detailOne.textContent).toContain("Trecho 1 do manual.");
    const link = detailOne.querySelector("a");
    expect(link?.getAttribute("href")).toBe("https://erp.example.com/doc");
    expect(link?.getAttribute("target")).toBe("_blank");
    expect(link?.getAttribute("rel")).toBe("noopener noreferrer");
    expect(link?.getAttribute("aria-label")).toBe("Abrir a fonte 1 em nova aba");

    toggle.click();
    await el.updateComplete;
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    expect(detailOne.hidden).toBe(true);

    const second = findByText(el, "[part=citations] button", "[2]");
    second.click();
    await el.updateComplete;
    expect(find(el, `#${second.id}-detail`).querySelector("a")).toBeNull();
    expect(text(el)).toContain("Fontes");
  });
});

describe("<knobridge-chat> history", () => {
  const history = detail([
    message({ id: "q1", content: "Como fecho o caixa?" }),
    message({
      id: "a1",
      position: 1,
      role: "assistant",
      content: "Pelo menu Caixa [1].",
      citations: [citation(1)],
    }),
    message({ id: "q2", position: 2, content: "E o estorno?" }),
    message({ id: "a2", position: 3, role: "assistant", content: "Par", status: "failed" }),
    message({ id: "q3", position: 4, content: "Ainda?" }),
    message({ id: "a3", position: 5, role: "assistant", content: "Até", status: "interrupted" }),
  ]);

  function seed(sub: string | null = null) {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        conversation_id: "c1",
        visitor_token: TOKEN,
        identity_sub: sub,
        saved_at: "2026-10-14T10:00:00.000Z",
      }),
    );
  }

  it("test_history_is_read_again_when_the_element_is_recreated", async () => {
    seed();
    const { calls } = installFetch({
      "GET /config": json(CONFIG),
      "GET /conversations/c1": history,
    });

    const first = await mount({ mode: "inline" });
    await vi.waitFor(() => {
      expect(text(first.el)).toContain("Pelo menu Caixa [1].");
    });
    first.el.remove();
    const second = await mount({ mode: "inline" });
    await vi.waitFor(() => {
      expect(text(second.el)).toContain("Como fecho o caixa?");
    });

    expect(text(second.el)).toContain("Não consegui responder agora.");
    expect(text(second.el)).toContain("A resposta foi interrompida.");
    expect(calls.filter((call) => call.path === "/conversations/c1")).toHaveLength(2);
    expect(calls[1]?.init.headers).toEqual({ Authorization: `Bearer ${TOKEN}` });
  });

  it("test_history_of_another_identity_is_ignored", async () => {
    seed("cliente-42");
    const { calls } = installFetch({ "GET /config": json(CONFIG) });

    const { el } = await mount({ mode: "inline" });

    expect(calls).toHaveLength(1);
    expect(root(el).querySelectorAll(".message")).toHaveLength(1);
  });

  it("test_history_not_found_forgets_the_pointer", async () => {
    seed();
    installFetch({
      "GET /config": json(CONFIG),
      "GET /conversations/c1": apiError(404, "not_found"),
    });

    const { el, events } = await mount({ mode: "inline" });

    expect(stored()).toBeNull();
    expect(events.at(-1)).toEqual({
      name: "knobridge-error",
      detail: { code: "not_found", status: 404 },
    });
    expect(root(el).querySelectorAll(".message")).toHaveLength(1);
  });

  it("test_history_network_failure_keeps_the_pointer", async () => {
    seed();
    installFetch({ "GET /config": json(CONFIG), "GET /conversations/c1": new TypeError("x") });

    await mount({ mode: "inline" });

    expect(stored()).not.toBeNull();
  });

  it("test_history_retry_resends_a_failed_question", async () => {
    seed();
    const { calls } = installFetch({
      "GET /config": json(CONFIG),
      "GET /conversations/c1": history,
      "POST /conversations/c1/messages": answer(["Estorno pelo menu."]),
    });
    const { el } = await mount({ mode: "inline" });
    await vi.waitFor(() => {
      expect(text(el)).toContain("E o estorno?");
    });

    find(el, ".retry").click();
    await settle(el);

    expect(calls.at(-1)?.init.body).toBe('{"content":"E o estorno?"}');
    expect(text(el)).toContain("Estorno pelo menu.");
    expect(text(el)).not.toContain("Par");
  });

  it("test_new_conversation_forgets_the_history_and_focuses_the_question", async () => {
    seed();
    installFetch({ "GET /config": json(CONFIG), "GET /conversations/c1": history });
    const { el } = await mount({ mode: "inline" });
    await vi.waitFor(() => {
      expect(text(el)).toContain("Como fecho o caixa?");
    });

    findByText(el, "header button", "Nova conversa").click();
    await el.updateComplete;
    await el.updateComplete;

    expect(stored()).toBeNull();
    expect(root(el).querySelectorAll(".message")).toHaveLength(1);
    expect(root(el).activeElement).toBe(find(el, "textarea"));
  });

  it("test_storage_none_keeps_nothing_in_the_browser", async () => {
    installFetch({
      "GET /config": json(CONFIG),
      "POST /conversations": created(),
      "POST /conversations/c1/messages": answer(["Ok."]),
    });
    const { el } = await mount({ mode: "inline", storage: "none" });

    await ask(el, "Oi");
    await settle(el);

    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBe(0);
  });
});
