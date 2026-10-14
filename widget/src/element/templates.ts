// Templates of a message: the answer's Markdown tree, the [n] markers, the "Fontes" list and the
// failure notices. Lit escapes every interpolated text, so nothing from the API becomes HTML.

import { html, nothing, type TemplateResult } from "lit";

import type { Citation } from "../api/types.ts";
import type { ViewMessage } from "../chat/controller.ts";
import type { Translate } from "../i18n/index.ts";
import { isHttpUrl, parseMarkdown, type Block, type Inline } from "../lib/markdown.ts";

export interface MessageContext {
  t: Translate;
  isExpanded(messageKey: string, index: number): boolean;
  toggleCitation(messageKey: string, index: number): void;
  /** From a [n] marker: expands the citation and moves the focus to it. */
  showCitation(messageKey: string, index: number): void;
  retry(messageKey: string): void;
  /** Extension point under each answer (feedback and "Abrir chamado" arrive in F4.2). */
  answerActions(message: ViewMessage): TemplateResult | typeof nothing;
}

type Rendered = TemplateResult | string | typeof nothing;

/** One answer being rendered: its message, the callbacks and the titles by citation index. */
interface Scope {
  message: ViewMessage;
  ctx: MessageContext;
  titles: ReadonlyMap<number, string>;
}

export function citationId(messageKey: string, index: number): string {
  return `cite-${messageKey}-${String(index)}`;
}

function renderInline(nodes: Inline[], scope: Scope): Rendered[] {
  const { message, ctx } = scope;
  return nodes.map((node): Rendered => {
    switch (node.type) {
      case "text":
        return node.text;
      case "break":
        return html`<br />`;
      case "strong":
        return html`<strong>${renderInline(node.children, scope)}</strong>`;
      case "em":
        return html`<em>${renderInline(node.children, scope)}</em>`;
      case "code":
        return html`<code>${node.text}</code>`;
      case "link":
        return html`<a href=${node.href} target="_blank" rel="noopener noreferrer"
          >${node.text}</a
        >`;
      case "cite": {
        const label = ctx.t("sourceLabel", {
          n: node.index,
          title: String(scope.titles.get(node.index)),
        });
        const show = () => {
          ctx.showCitation(message.key, node.index);
        };
        // The marker sits inside a sentence: Prettier would add whitespace around "[n]".
        // prettier-ignore
        return html`<button type="button" class="cite" aria-label=${label} @click=${show}>[${node.index}]</button>`;
      }
    }
  });
}

function renderBlock(block: Block, scope: Scope): TemplateResult {
  switch (block.type) {
    case "paragraph":
      return html`<p>${renderInline(block.children, scope)}</p>`;
    case "heading":
      return html`<p><strong>${renderInline(block.children, scope)}</strong></p>`;
    case "code":
      return html`<pre><code>${block.text}</code></pre>`;
    case "list": {
      const items = block.items.map((item) => html`<li>${renderInline(item, scope)}</li>`);
      return block.ordered
        ? html`<ol>
            ${items}
          </ol>`
        : html`<ul>
            ${items}
          </ul>`;
    }
  }
}

function renderCitation(citation: Citation, message: ViewMessage, ctx: MessageContext) {
  const id = citationId(message.key, citation.index);
  const expanded = ctx.isExpanded(message.key, citation.index);
  return html`<li>
    <button
      type="button"
      id=${id}
      aria-expanded=${expanded ? "true" : "false"}
      aria-controls=${`${id}-detail`}
      @click=${() => {
        ctx.toggleCitation(message.key, citation.index);
      }}
    >
      [${citation.index}] ${citation.title}
    </button>
    <div class="detail" id=${`${id}-detail`} ?hidden=${!expanded}>
      ${citation.snippet}
      ${
        isHttpUrl(citation.url)
          ? html`<div>
              <a
                href=${citation.url}
                target="_blank"
                rel="noopener noreferrer"
                aria-label=${ctx.t("openSourceLabel", { n: citation.index })}
                >${ctx.t("openSource")}</a
              >
            </div>`
          : nothing
      }
    </div>
  </li>`;
}

function renderFailure(message: ViewMessage, ctx: MessageContext): Rendered {
  const failure = message.failure;
  if (!failure) return nothing;
  if (failure.kind === "rate_limited") {
    return html`<p class="notice">
      ${
        failure.minutes === 1
          ? ctx.t("rateLimitedOne")
          : ctx.t("rateLimited", { minutes: failure.minutes })
      }
    </p>`;
  }
  if (failure.kind === "unavailable") return html`<p class="notice">${ctx.t("unavailable")}</p>`;
  return html`<p class="notice">${ctx.t("failed")}</p>
    <button
      type="button"
      class="retry"
      @click=${() => {
        ctx.retry(message.key);
      }}
    >
      ${ctx.t("retry")}
    </button>`;
}

export function renderMessage(message: ViewMessage, ctx: MessageContext): TemplateResult {
  if (message.role === "user") {
    return html`<div part="message" class="message user">
      <span class="sr-only">${ctx.t("you")}:</span> ${message.content}
    </div>`;
  }
  const streaming = message.status === "streaming";
  const titles = new Map(message.citations.map((citation) => [citation.index, citation.title]));
  return html`<div
    part="message"
    class="message assistant"
    aria-busy=${streaming ? "true" : "false"}
  >
    <span class="sr-only">${ctx.t("assistant")}:</span>
    ${streaming && !message.content ? html`<p class="typing">${ctx.t("typing")}</p>` : nothing}
    ${parseMarkdown(message.content, titles).map((block) => renderBlock(block, { message, ctx, titles }))}
    ${
      message.status === "interrupted"
        ? html`<p class="notice">${ctx.t("interrupted")}</p>`
        : nothing
    }
    ${renderFailure(message, ctx)}
    ${
      message.citations.length
        ? html`<div part="citations" class="sources">
            <h3>${ctx.t("sources")}</h3>
            <ul>
              ${message.citations.map((citation) => renderCitation(citation, message, ctx))}
            </ul>
          </div>`
        : nothing
    }
    ${streaming ? nothing : ctx.answerActions(message)}
  </div>`;
}

/** The greeting is shown as the first answer, but it is never part of the conversation. */
export function renderGreeting(greeting: string, ctx: MessageContext): Rendered {
  if (!greeting) return nothing;
  return html`<div part="message" class="message assistant">
    <span class="sr-only">${ctx.t("assistant")}:</span>
    <p>${greeting}</p>
  </div>`;
}
