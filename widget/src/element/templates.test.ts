import { html, nothing, render } from "lit";
import { describe, expect, it, vi } from "vitest";

import type { ViewMessage } from "../chat/controller.ts";
import { translator } from "../i18n/index.ts";
import { citation } from "../test/fake-api.ts";
import { renderGreeting, renderMessage, type MessageContext } from "./templates.ts";

function context(overrides: Partial<MessageContext> = {}): MessageContext {
  return {
    t: translator("pt-BR"),
    isExpanded: () => false,
    toggleCitation: vi.fn(),
    showCitation: vi.fn(),
    retry: vi.fn(),
    answerActions: () => nothing,
    ...overrides,
  };
}

function assistant(content: string, overrides: Partial<ViewMessage> = {}): ViewMessage {
  return {
    key: "m2",
    id: "a1",
    role: "assistant",
    content,
    status: "completed",
    citations: [citation(1)],
    failure: null,
    question: "Como?",
    feedback: null,
    ticketRequest: null,
    ...overrides,
  };
}

function mount(template: unknown): HTMLElement {
  const container = document.createElement("div");
  render(template, container);
  return container;
}

describe("renderMessage", () => {
  it("test_render_message_draws_the_markdown_subset", () => {
    const content = [
      "## Passos",
      "Primeiro *abra* o `menu`,",
      "depois veja [o guia](https://x.com/guia) [1].",
      "",
      "- um",
      "- dois",
      "",
      "1. três",
      "",
      "```",
      "select 1;",
      "```",
    ].join("\n");

    const container = mount(renderMessage(assistant(content), context()));

    expect(container.querySelector("p strong")?.textContent).toBe("Passos");
    expect(container.querySelector("em")?.textContent).toBe("abra");
    expect(container.querySelector("code")?.textContent).toBe("menu");
    expect(container.querySelector("br")).not.toBeNull();
    expect(container.querySelector("a[href='https://x.com/guia']")?.getAttribute("rel")).toBe(
      "noopener noreferrer",
    );
    expect(container.querySelectorAll(".message > ul > li")).toHaveLength(2);
    expect(container.querySelectorAll("ol > li")).toHaveLength(1);
    expect(container.querySelector("pre code")?.textContent).toBe("select 1;");
  });

  it("test_render_message_marker_calls_show_citation", () => {
    const showCitation = vi.fn();
    const container = mount(renderMessage(assistant("Veja [1]."), context({ showCitation })));

    container.querySelector<HTMLButtonElement>("button.cite")?.click();

    expect(showCitation).toHaveBeenCalledWith("m2", 1);
  });

  it("test_render_message_shows_answer_actions_only_when_finished", () => {
    const answerActions = vi.fn(() => html`<span class="actions">ações</span>`);

    const done = mount(renderMessage(assistant("Ok."), context({ answerActions })));
    const streaming = mount(
      renderMessage(assistant("", { status: "streaming" }), context({ answerActions })),
    );

    expect(done.querySelector(".actions")).not.toBeNull();
    expect(streaming.querySelector(".actions")).toBeNull();
    expect(streaming.querySelector(".typing")?.textContent).toBe("Digitando…");
  });

  it("test_render_message_of_the_visitor_is_plain_text", () => {
    const container = mount(
      renderMessage(assistant("**não** é markdown", { role: "user", citations: [] }), context()),
    );

    expect(container.querySelector("strong")).toBeNull();
    expect(container.textContent).toContain("Você:");
  });
});

describe("renderGreeting", () => {
  it("test_render_greeting_is_empty_without_text", () => {
    expect(renderGreeting("", context())).toBe(nothing);
    expect(mount(renderGreeting("Olá", context())).textContent).toContain("Olá");
  });
});
