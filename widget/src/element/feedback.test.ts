import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import "../index.ts";
import { resetMemoryStorage } from "../lib/storage.ts";
import { ask, find, findByText, mount, root, settle, text } from "../test/dom.ts";
import {
  answer,
  apiError,
  citation,
  CONFIG,
  created,
  detail,
  installFetch,
  json,
  KEY,
  message,
  TOKEN,
} from "../test/fake-api.ts";

const FEEDBACK = "POST /conversations/c1/messages/a1/feedback";

beforeEach(() => {
  localStorage.clear();
  resetMemoryStorage();
});

afterEach(() => {
  document.body.replaceChildren();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function rateButton(el: Element, label: "Resposta útil" | "Resposta não útil"): HTMLButtonElement {
  return find(el, `button[aria-label="${label}"]`) as HTMLButtonElement;
}

async function answered(routes: Parameters<typeof installFetch>[0] = {}, config = CONFIG) {
  const fake = installFetch({
    "GET /config": json(config),
    "POST /conversations": created(),
    "POST /conversations/c1/messages": answer(["Pelo menu Caixa [1]."], {
      citations: [citation(1)],
    }),
    ...routes,
  });
  const mounted = await mount({ mode: "inline" });
  await ask(mounted.el, "Como fecho o caixa?");
  await settle(mounted.el);
  return { ...fake, ...mounted };
}

describe("<knobridge-chat> feedback", () => {
  it("test_feedback_up_is_saved_pressed_and_announced_by_event", async () => {
    const { el, events, calls } = await answered({
      [FEEDBACK]: json({ rating: "up", comment: null }),
    });
    const up = rateButton(el, "Resposta útil");
    expect(up.getAttribute("aria-pressed")).toBe("false");
    expect(find(el, "[role=group]").getAttribute("aria-label")).toBe("Ações da resposta");

    up.click();
    await vi.waitFor(() => {
      expect(rateButton(el, "Resposta útil").getAttribute("aria-pressed")).toBe("true");
    });

    expect(rateButton(el, "Resposta não útil").getAttribute("aria-pressed")).toBe("false");
    expect(calls.at(-1)?.init.headers).toMatchObject({ Authorization: `Bearer ${TOKEN}` });
    expect(events.at(-1)).toEqual({
      name: "knobridge-feedback",
      detail: { messageId: "a1", rating: "up" },
    });
    expect(root(el).querySelector(".inline-form")).toBeNull();
  });

  it("test_feedback_down_opens_an_optional_comment", async () => {
    const { el, calls } = await answered({
      [FEEDBACK]: [
        json({ rating: "down", comment: null }),
        json({ rating: "down", comment: "Faltou o estorno" }),
      ],
    });

    rateButton(el, "Resposta não útil").click();
    await vi.waitFor(() => {
      expect(text(el)).toContain("O que faltou na resposta? (opcional)");
    });
    const comment = find(el, "textarea[id^=comment-]") as HTMLTextAreaElement;
    expect(comment.maxLength).toBe(2000);
    comment.value = "Faltou o estorno";
    comment.dispatchEvent(new Event("input", { bubbles: true, composed: true }));
    findByText(el, "button", "Enviar comentário").click();
    await vi.waitFor(() => {
      expect(text(el)).toContain("Obrigado pelo comentário.");
    });

    expect(calls.at(-1)?.init.body).toBe('{"rating":"down","comment":"Faltou o estorno"}');
    expect(root(el).querySelector("textarea[id^=comment-]")).toBeNull();
    expect(rateButton(el, "Resposta não útil").getAttribute("aria-pressed")).toBe("true");
  });

  it("test_feedback_rate_limited_shows_the_wait", async () => {
    const { el, events } = await answered({
      [FEEDBACK]: apiError(429, "rate_limited", { "Retry-After": "300" }),
    });

    rateButton(el, "Resposta útil").click();
    await vi.waitFor(() => {
      expect(text(el)).toContain("Tente de novo em 5 minutos.");
    });

    expect(find(el, ".answer-actions [role=alert]").textContent).toContain("Muitas mensagens");
    expect(events.at(-1)).toEqual({
      name: "knobridge-error",
      detail: { code: "rate_limited", status: 429 },
    });
    expect(rateButton(el, "Resposta útil").getAttribute("aria-pressed")).toBe("false");
  });

  it.each([
    [new TypeError("offline"), "Não consegui registrar sua avaliação. Tente de novo."],
    [apiError(409, "feedback_disabled"), "A avaliação não está disponível."],
    [apiError(429, "rate_limited", { "Retry-After": "30" }), "Tente de novo em 1 minuto."],
  ])("test_feedback_failure_%#_shows_a_notice", async (reply, notice) => {
    const { el } = await answered({ [FEEDBACK]: reply });

    rateButton(el, "Resposta não útil").click();
    await vi.waitFor(() => {
      expect(text(el)).toContain(notice);
    });

    expect(root(el).querySelector("textarea[id^=comment-]")).toBeNull();
  });

  it("test_feedback_off_in_the_panel_shows_no_buttons", async () => {
    const { el } = await answered(
      {},
      { ...CONFIG, feedback_enabled: false, ticket_enabled: false },
    );

    expect(root(el).querySelector("button[aria-label='Resposta útil']")).toBeNull();
    expect(root(el).querySelector("[role=group]")?.children).toHaveLength(0);
  });

  it("test_feedback_comes_back_with_the_history", async () => {
    localStorage.setItem(
      `knobridge:v1:${KEY}`,
      JSON.stringify({
        conversation_id: "c1",
        visitor_token: TOKEN,
        identity_sub: null,
        saved_at: "2026-10-14T10:00:00.000Z",
      }),
    );
    installFetch({
      "GET /config": json(CONFIG),
      "GET /conversations/c1": detail([
        message({ id: "q1", content: "Como?" }),
        message({
          id: "a1",
          position: 1,
          role: "assistant",
          content: "Assim [1].",
          citations: [citation(1)],
          feedback: { rating: "down", comment: "Curta" },
        }),
        message({ id: "q2", position: 2, content: "E?" }),
        message({ id: "a2", position: 3, role: "assistant", content: "Fal", status: "failed" }),
      ]),
    });

    const { el } = await mount({ mode: "inline" });
    await vi.waitFor(() => {
      expect(text(el)).toContain("Assim [1].");
    });

    expect(rateButton(el, "Resposta não útil").getAttribute("aria-pressed")).toBe("true");
    // Feedback only on completed and no-source answers: the failed one has none.
    expect(root(el).querySelectorAll("button[aria-label='Resposta útil']")).toHaveLength(1);
  });
});
