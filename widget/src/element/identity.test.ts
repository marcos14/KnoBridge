import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import "../index.ts";
import { resetMemoryStorage } from "../lib/storage.ts";
import { ask, mount, root, settle, text } from "../test/dom.ts";
import {
  ANA,
  answer,
  CONFIG,
  created,
  detail,
  IDENTITY,
  identityOf,
  installFetch,
  json,
  KEY,
  message,
  OTHER_TOKEN,
  sentBody,
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

describe("<knobridge-chat> signed identity", () => {
  it("test_identity_attribute_is_passed_through_on_the_first_question", async () => {
    const { calls } = installFetch({
      "GET /config": json(CONFIG),
      "POST /conversations": created("c1", TOKEN, ANA),
      "POST /conversations/c1/messages": answer(["Olá, Ana."]),
    });
    const { el, events } = await mount({ mode: "inline", identity: IDENTITY });

    await ask(el, "Oi");
    await settle(el);

    expect(calls[1]?.init.body).toBe(JSON.stringify({ identity: IDENTITY }));
    // Only the conversation route takes the identity; the question goes with the token.
    expect(calls[2]?.init.body).toBe('{"content":"Oi"}');
    expect(stored()).toMatchObject({ conversation_id: "c1", identity_sub: "cliente-42" });
    // Never in the browser storage nor in an event.
    expect(localStorage.getItem(STORAGE_KEY)).not.toContain(IDENTITY);
    expect(JSON.stringify(events)).not.toContain(IDENTITY);
  });

  it("test_set_identity_of_another_person_opens_another_conversation", async () => {
    const { calls } = installFetch({
      "GET /config": json(CONFIG),
      "POST /conversations": [created("c1", TOKEN, ANA), created("c2", OTHER_TOKEN)],
      "POST /conversations/c1/messages": answer(["Olá, Ana."]),
      "POST /conversations/c2/messages": answer(["Olá, Bia."], { id: "b1" }),
    });
    const { el } = await mount({ mode: "inline", identity: IDENTITY });
    await ask(el, "Oi");
    await settle(el);
    const other = identityOf({ sub: "cliente-77", iat: 1, exp: 2 });

    el.setIdentity(other);
    await el.updateComplete;
    await vi.waitFor(() => {
      expect(text(el)).not.toContain("Olá, Ana.");
    });
    await ask(el, "Oi de novo");
    await settle(el);

    expect(calls.filter((call) => call.path === "/conversations")).toHaveLength(2);
    expect(calls.find((call) => call.path === "/conversations/c2/messages")).toBeDefined();
    expect(sentBody(calls[3])).toEqual({ identity: other });
    expect(stored()).toMatchObject({ conversation_id: "c2", identity_sub: "cliente-77" });
    expect(text(el)).toContain("Olá, Bia.");
  });

  it("test_identity_attribute_renewed_for_the_same_person_keeps_the_conversation", async () => {
    const { calls } = installFetch({
      "GET /config": json(CONFIG),
      "POST /conversations": created("c1", TOKEN, ANA),
      "POST /conversations/c1/messages": answer(["Olá, Ana."]),
    });
    const { el } = await mount({ mode: "inline", identity: IDENTITY });
    await ask(el, "Oi");
    await settle(el);

    el.setAttribute("identity", identityOf({ sub: "cliente-42", iat: 5 }));
    await el.updateComplete;

    expect(text(el)).toContain("Olá, Ana.");
    expect(calls).toHaveLength(3);
  });

  it("test_identity_restores_only_the_conversation_of_the_same_sub", async () => {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        conversation_id: "c1",
        visitor_token: TOKEN,
        identity_sub: "cliente-42",
        saved_at: "2026-10-14T10:00:00.000Z",
      }),
    );
    installFetch({
      "GET /config": json(CONFIG),
      "GET /conversations/c1": detail(
        [message({ id: "q1", content: "Pergunta da Ana" })],
        "c1",
        ANA,
      ),
    });

    const anonymous = await mount({ mode: "inline" });
    expect(text(anonymous.el)).not.toContain("Pergunta da Ana");

    anonymous.el.setIdentity(IDENTITY);
    await vi.waitFor(() => {
      expect(text(anonymous.el)).toContain("Pergunta da Ana");
    });

    anonymous.el.setIdentity(null);
    await vi.waitFor(() => {
      expect(text(anonymous.el)).not.toContain("Pergunta da Ana");
    });
    expect(root(anonymous.el).querySelectorAll(".message")).toHaveLength(1);
  });
});
