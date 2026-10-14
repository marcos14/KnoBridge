// DOM helpers for the element tests: mount <knobridge-chat>, query its shadow root, type and
// collect the events it emits.

import { expect, vi } from "vitest";

import type { KnoBridgeChat } from "../element/knobridge-chat.ts";
import { API, KEY } from "./fake-api.ts";

export function root(el: Element): ShadowRoot {
  if (!el.shadowRoot) throw new Error("no shadow root");
  return el.shadowRoot;
}

function required<T>(found: T | null, selector: string): T {
  if (!found) throw new Error(`nothing matches ${selector}`);
  return found;
}

export function find(el: Element, selector: string): HTMLElement {
  return required(root(el).querySelector<HTMLElement>(selector), selector);
}

export function textarea(el: Element): HTMLTextAreaElement {
  return required(root(el).querySelector<HTMLTextAreaElement>("#input"), "#input");
}

export function form(el: Element): HTMLFormElement {
  return required(root(el).querySelector<HTMLFormElement>("form[part=composer]"), "composer");
}

export function sendButton(el: Element): HTMLButtonElement {
  return required(root(el).querySelector<HTMLButtonElement>(".send"), ".send");
}

export function findByText(el: Element, selector: string, text: string): HTMLElement {
  const found = [...root(el).querySelectorAll<HTMLElement>(selector)].find((node) =>
    node.textContent.includes(text),
  );
  if (!found) throw new Error(`no ${selector} with "${text}"`);
  return found;
}

/** The rendered text, without the <style> Lit adds when the DOM has no adoptedStyleSheets. */
export function text(el: Element): string {
  return [...root(el).children]
    .filter((child) => child.tagName !== "STYLE")
    .map((child) => child.textContent)
    .join(" ")
    .replace(/\s+/g, " ");
}

/** The rendered elements, without Lit's <style>. */
export function rendered(el: Element): Element[] {
  return [...root(el).children].filter((child) => child.tagName !== "STYLE");
}

export interface Recorded {
  name: string;
  detail: Record<string, unknown>;
}

export const EVENT_NAMES = [
  "knobridge-ready",
  "knobridge-open",
  "knobridge-close",
  "knobridge-message-sent",
  "knobridge-answer",
  "knobridge-feedback",
  "knobridge-ticket-requested",
  "knobridge-error",
] as const;

/** Creates the element (not yet in the page) and records every knobridge-* event. */
export function create(attributes: Record<string, string> = {}) {
  const el = document.createElement("knobridge-chat");
  const all: Record<string, string> = { "widget-key": KEY, "api-base": API, ...attributes };
  for (const [name, value] of Object.entries(all)) el.setAttribute(name, value);
  const events: Recorded[] = [];
  for (const name of EVENT_NAMES) {
    el.addEventListener(name, (event) => {
      events.push({ name, detail: (event as CustomEvent<Record<string, unknown>>).detail });
    });
  }
  return { el, events };
}

/** Mounts the element and waits for the configuration (and the history, when there is one). */
export async function mount(attributes: Record<string, string> = {}) {
  const created = create(attributes);
  document.body.append(created.el);
  await vi.waitFor(() => {
    expect(created.events.some((event) => event.name === "knobridge-ready")).toBe(true);
  });
  await settle(created.el);
  return created;
}

/** Waits until no question is pending and the element rendered its last state. */
export async function settle(el: KnoBridgeChat): Promise<void> {
  // A pending render may still show the previous state; let it land first.
  await el.updateComplete;
  await vi.waitFor(() => {
    expect(textarea(el).readOnly).toBe(false);
  });
  await el.updateComplete;
}

export async function type(el: KnoBridgeChat, value: string): Promise<HTMLTextAreaElement> {
  const input = textarea(el);
  input.value = value;
  input.dispatchEvent(new Event("input", { bubbles: true, composed: true }));
  await el.updateComplete;
  return input;
}

export function press(target: Element, key: string, options: KeyboardEventInit = {}): void {
  target.dispatchEvent(
    new KeyboardEvent("keydown", { key, bubbles: true, composed: true, ...options }),
  );
}

/** Types and presses Enter, the way a visitor sends a question. */
export async function ask(el: KnoBridgeChat, question: string): Promise<void> {
  const input = await type(el, question);
  press(input, "Enter");
  await el.updateComplete;
}
