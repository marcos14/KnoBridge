import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import "../index.ts";
import { resetMemoryStorage } from "../lib/storage.ts";
import { ask, find, findByText, mount, root, settle, text } from "../test/dom.ts";
import {
  ANA,
  answer,
  apiError,
  CONFIG,
  created,
  detail,
  IDENTITY,
  installFetch,
  json,
  KEY,
  message,
  sentBody,
  ticketRequest,
  TOKEN,
} from "../test/fake-api.ts";
import type { KnoBridgeChat } from "./knobridge-chat.ts";

const TICKETS = "POST /conversations/c1/ticket-requests";

beforeEach(() => {
  localStorage.clear();
  resetMemoryStorage();
});

afterEach(() => {
  vi.useRealTimers();
  document.body.replaceChildren();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

type Routes = Parameters<typeof installFetch>[0];

async function noSource(routes: Routes = {}, attributes: Record<string, string> = {}) {
  const fake = installFetch({
    "GET /config": json(CONFIG),
    "POST /conversations": created("c1", TOKEN, attributes.identity ? ANA : null),
    "POST /conversations/c1/messages": answer(["Não encontrei isso."], { status: "no_source" }),
    ...routes,
  });
  const mounted = await mount({ mode: "inline", ...attributes });
  await ask(mounted.el, "Como fecho o caixa?");
  await settle(mounted.el);
  return { ...fake, ...mounted };
}

function field(el: Element, name: "summary" | "email" | "name"): HTMLInputElement {
  return find(el, `[id$=-${name}]`) as HTMLInputElement;
}

async function fill(el: KnoBridgeChat, name: "summary" | "email" | "name", value: string) {
  const input = field(el, name);
  input.value = value;
  input.dispatchEvent(new Event("input", { bubbles: true, composed: true }));
  await el.updateComplete;
}

async function openForm(el: KnoBridgeChat) {
  findByText(el, "button", "Abrir chamado").click();
  await vi.waitFor(() => {
    expect(root(el).querySelector("[part=ticket-form]")).not.toBeNull();
  });
}

async function submit(el: KnoBridgeChat) {
  findByText(el, "button", "Enviar pedido").click();
  await el.updateComplete;
}

describe("<knobridge-chat> ticket", () => {
  it("test_ticket_form_fills_the_summary_and_asks_the_email_of_an_anonymous_visitor", async () => {
    const { el } = await noSource();
    expect(find(el, ".ticket").classList.contains("primary")).toBe(true);

    await openForm(el);

    expect(text(el)).toContain(
      "Vamos enviar sua pergunta, este resumo e a conversa para a equipe de suporte.",
    );
    expect(field(el, "summary").value).toBe("Como fecho o caixa?");
    expect(field(el, "email").type).toBe("email");
    expect(field(el, "name").value).toBe("");
    await vi.waitFor(() => {
      expect(root(el).activeElement).toBe(field(el, "summary"));
    });
    expect(root(el).querySelector(".ticket")).toBeNull();
  });

  it("test_ticket_requires_a_valid_email_and_focuses_it", async () => {
    const { el, calls } = await noSource();
    await openForm(el);
    const before = calls.length;

    await submit(el);
    await vi.waitFor(() => {
      expect(root(el).activeElement).toBe(field(el, "email"));
    });

    const email = field(el, "email");
    expect(email.getAttribute("aria-invalid")).toBe("true");
    const error = find(el, `#${email.getAttribute("aria-describedby") ?? ""}`);
    expect(error.textContent).toBe("Informe um e-mail válido.");
    expect(field(el, "summary").getAttribute("aria-invalid")).toBe("false");
    expect(calls).toHaveLength(before);
  });

  it("test_ticket_summary_and_name_errors_are_shown", async () => {
    const { el } = await noSource();
    await openForm(el);
    await fill(el, "summary", " ");
    await fill(el, "email", "ana@exemplo.com.br");
    await fill(el, "name", "x".repeat(201));

    await submit(el);
    await vi.waitFor(() => {
      expect(root(el).activeElement).toBe(field(el, "summary"));
    });

    expect(text(el)).toContain("Escreva um resumo de até 2000 caracteres.");
    expect(text(el)).toContain("O nome pode ter até 200 caracteres.");
  });

  it("test_ticket_is_requested_with_the_typed_email_and_emits_the_event", async () => {
    const { el, events, calls } = await noSource({ [TICKETS]: json(ticketRequest(), 202) });
    await openForm(el);
    await fill(el, "summary", "Fechamento do caixa");
    await fill(el, "email", "ana@exemplo.com.br");
    await fill(el, "name", "Ana");

    await submit(el);
    await vi.waitFor(() => {
      expect(text(el)).toContain("Chamado solicitado.");
    });

    expect(sentBody(calls.at(-1))).toEqual({
      message_id: "a1",
      summary: "Fechamento do caixa",
      email: "ana@exemplo.com.br",
      name: "Ana",
    });
    expect(events.at(-1)).toEqual({
      name: "knobridge-ticket-requested",
      detail: { ticketRequestId: "t1", messageId: "a1" },
    });
    expect(root(el).querySelector("[part=ticket-form]")).toBeNull();
    expect(root(el).querySelector(".ticket")).toBeNull();
  });

  it("test_ticket_with_the_identity_email_hides_email_and_name", async () => {
    const { el, calls } = await noSource(
      { [TICKETS]: json(ticketRequest(), 202) },
      { identity: IDENTITY },
    );
    await openForm(el);

    expect(root(el).querySelector("[id$=-email]")).toBeNull();
    expect(root(el).querySelector("[id$=-name]")).toBeNull();
    await submit(el);
    await vi.waitFor(() => {
      expect(text(el)).toContain("Chamado solicitado.");
    });

    expect(sentBody(calls.at(-1))).toMatchObject({ email: null, name: null });
  });

  it.each([
    [
      apiError(429, "rate_limited", { "Retry-After": "3600" }),
      "Tente de novo em 60 minutos.",
      true,
    ],
    [apiError(409, "ticket_request_exists"), "Já existe um chamado para esta resposta.", false],
    [apiError(409, "ticket_webhook_not_configured"), "Abrir chamado não está disponível.", false],
    [apiError(422, "validation_error"), "Confira os dados e tente de novo.", true],
    [new TypeError("offline"), "Não consegui enviar o pedido. Tente de novo.", true],
  ])("test_ticket_failure_%#_is_shown", async (reply, notice, formStays) => {
    const { el, events } = await noSource({ [TICKETS]: reply });
    await openForm(el);
    await fill(el, "email", "ana@exemplo.com.br");

    await submit(el);
    await vi.waitFor(() => {
      expect(text(el)).toContain(notice);
    });

    expect(find(el, ".answer-actions [role=alert]").textContent).toContain(notice);
    expect(root(el).querySelector("[part=ticket-form]") !== null).toBe(formStays);
    expect(root(el).querySelector(".ticket") !== null).toBe(false);
    expect(events.at(-1)?.name).toBe("knobridge-error");
  });

  it("test_ticket_cancel_closes_the_form", async () => {
    const { el } = await noSource();
    await openForm(el);

    findByText(el, "button", "Cancelar").click();
    await el.updateComplete;

    expect(root(el).querySelector("[part=ticket-form]")).toBeNull();
    expect(findByText(el, "button", "Abrir chamado")).toBeTruthy();
  });

  it("test_ticket_on_a_completed_answer_is_a_secondary_button", async () => {
    installFetch({
      "GET /config": json(CONFIG),
      "POST /conversations": created(),
      "POST /conversations/c1/messages": answer(["Pelo menu."]),
    });
    const { el } = await mount({ mode: "inline" });
    await ask(el, "Como?");
    await settle(el);

    expect(find(el, ".ticket").classList.contains("primary")).toBe(false);
  });

  it("test_ticket_hidden_when_off_in_the_panel_or_in_the_answer", async () => {
    const off = await noSource({ "GET /config": json({ ...CONFIG, ticket_enabled: false }) });
    expect(root(off.el).querySelector(".ticket")).toBeNull();
    off.el.remove();
    localStorage.clear();

    installFetch({
      "GET /config": json(CONFIG),
      "POST /conversations": created(),
      "POST /conversations/c1/messages": () =>
        new Response(
          [
            "event: citations",
            'data: {"message_id":"a1","user_message_id":"q1","citations":[]}',
            "",
            "event: done",
            'data: {"message_id":"a1","status":"no_source","ticket_requests_enabled":false}',
            "",
            "",
          ].join("\n"),
          { headers: { "Content-Type": "text/event-stream" } },
        ),
    });
    const { el } = await mount({ mode: "inline" });
    await ask(el, "Como?");
    await settle(el);

    // The answer has its actions, only without the ticket.
    expect(root(el).querySelector("button[aria-label='Resposta útil']")).not.toBeNull();
    expect(root(el).querySelector(".ticket")).toBeNull();
  });

  it("test_ticket_status_comes_back_with_the_history", async () => {
    localStorage.setItem(
      `knobridge:v1:${KEY}`,
      JSON.stringify({
        conversation_id: "c1",
        visitor_token: TOKEN,
        identity_sub: null,
        saved_at: "2026-10-14T10:00:00.000Z",
      }),
    );
    const delivered = ticketRequest({
      status: "delivered",
      external_ticket_id: "SUP-7",
      external_url: "https://suporte.example.com/7",
    });
    installFetch({
      "GET /config": json(CONFIG),
      "GET /conversations/c1": detail([
        message({ id: "q1", content: "Um?" }),
        message({ id: "a1", position: 1, role: "assistant", status: "no_source", content: "N" }),
        message({ id: "q2", position: 2, content: "Dois?" }),
        message({
          id: "a2",
          position: 3,
          role: "assistant",
          status: "no_source",
          content: "N",
          ticket_request: delivered,
        }),
        message({ id: "q3", position: 4, content: "Três?" }),
        message({
          id: "a3",
          position: 5,
          role: "assistant",
          status: "no_source",
          content: "N",
          ticket_request: { ...delivered, external_ticket_id: null, external_url: "javascript:x" },
        }),
        message({ id: "q4", position: 6, content: "Quatro?" }),
        message({
          id: "a4",
          position: 7,
          role: "assistant",
          status: "no_source",
          content: "N",
          ticket_request: ticketRequest({ status: "failed" }),
        }),
      ]),
    });

    const { el } = await mount({ mode: "inline" });
    await vi.waitFor(() => {
      expect(text(el)).toContain("Chamado SUP-7 aberto.");
    });

    const link = findByText(el, "a", "Ver o chamado") as HTMLAnchorElement;
    expect(link.href).toBe("https://suporte.example.com/7");
    expect(link.target).toBe("_blank");
    expect(link.rel).toBe("noopener noreferrer");
    expect(root(el).querySelectorAll("a")).toHaveLength(1);
    expect(text(el)).toContain("Chamado aberto.");
    expect(text(el)).toContain("Não consegui abrir o chamado. Tente mais tarde.");
    // Only the answer without a request still offers one.
    expect(root(el).querySelectorAll(".ticket")).toHaveLength(1);
  });

  it("test_ticket_request_is_followed_until_the_number_arrives", async () => {
    const { el } = await noSource({
      [TICKETS]: json(ticketRequest(), 202),
      "GET /conversations/c1/ticket-requests/t1": json(
        ticketRequest({ status: "delivered", external_ticket_id: "SUP-8" }),
      ),
    });
    await openForm(el);
    await fill(el, "email", "ana@exemplo.com.br");
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });

    await submit(el);
    await vi.waitFor(() => {
      expect(text(el)).toContain("Chamado solicitado.");
    });
    await vi.advanceTimersByTimeAsync(10_000);
    await vi.waitFor(() => {
      expect(text(el)).toContain("Chamado SUP-8 aberto.");
    });
  });

  it("test_new_conversation_stops_following_the_request", async () => {
    const { el, calls } = await noSource({ [TICKETS]: json(ticketRequest(), 202) });
    await openForm(el);
    await fill(el, "email", "ana@exemplo.com.br");
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    await submit(el);
    await vi.waitFor(() => {
      expect(text(el)).toContain("Chamado solicitado.");
    });
    const before = calls.length;

    el.newConversation();
    await vi.advanceTimersByTimeAsync(60_000);

    expect(calls).toHaveLength(before);
  });
});
