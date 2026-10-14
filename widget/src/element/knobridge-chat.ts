// <knobridge-chat>: the embeddable chat of a KnoBridge product (docs/specs/widget.md, "Embutir o
// elemento"). Bubble or inline mode, configuration from GET /config, history through the
// browser pointer, answers streamed by SSE, feedback and "Abrir chamado" under each answer, and the
// signed identity passed through to the server as given.

import { html, LitElement, nothing, svg, type PropertyValues, type TemplateResult } from "lit";
import { styleMap } from "lit/directives/style-map.js";

import { asApiError, WidgetApi } from "../api/client.ts";
import type { WidgetPublicConfig } from "../api/types.ts";
import { ChatController } from "../chat/controller.ts";
import { translator, type Translate } from "../i18n/index.ts";
import { apiOrigin, contrastColor, isWidgetKey, pick, STORAGES } from "../lib/appearance.ts";
import { ConversationStore } from "../lib/storage.ts";
import { renderAnswerActions, type ActionsContext } from "./actions.ts";
import { renderComposer } from "./composer.ts";
import { styles } from "./styles.ts";
import { citationId, renderGreeting, renderMessage, type MessageContext } from "./templates.ts";
import { resolveView, type View } from "./view.ts";

let scriptOrigin: string | null = null;

/** Set once by the entry point, from the <script> that loaded the bundle. */
export function setScriptOrigin(origin: string | null): void {
  scriptOrigin = origin;
}

const CHAT_ICON = svg`<svg viewBox="0 0 24 24" width="26" height="26" aria-hidden="true" focusable="false"><path fill="currentColor" d="M4 4h16a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H8l-4 4V6a2 2 0 0 1 2-2z"/></svg>`;
const CLOSE_ICON = svg`<svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true" focusable="false"><path fill="currentColor" d="M6.4 5 12 10.6 17.6 5 19 6.4 13.4 12l5.6 5.6-1.4 1.4L12 13.4 6.4 19 5 17.6l5.6-5.6L5 6.4z"/></svg>`;

const APPEARANCE = [
  "mode",
  "position",
  "theme",
  "primaryColor",
  "chatTitle",
  "greeting",
  "placeholder",
  "config",
] as const;

export class KnoBridgeChat extends LitElement {
  static override styles = styles;

  static override properties = {
    widgetKey: { attribute: "widget-key" },
    apiBase: { attribute: "api-base" },
    mode: {},
    position: {},
    theme: {},
    primaryColor: { attribute: "primary-color" },
    // `title` is the HTMLElement tooltip property; the attribute keeps the spec's name.
    chatTitle: { attribute: "title" },
    greeting: {},
    placeholder: {},
    storage: {},
    // `v1.<payload>.<signature>` from the host's server, passed through as given.
    identity: {},
    // The `open` attribute; the property cannot be `open`, the name of the method.
    isOpen: { type: Boolean, attribute: "open", reflect: true },
    config: { state: true },
    configFailed: { state: true },
    draft: { state: true },
    expanded: { state: true },
  };

  declare widgetKey: string | null;
  declare apiBase: string | null;
  declare mode: string | null;
  declare position: string | null;
  declare theme: string | null;
  declare primaryColor: string | null;
  declare chatTitle: string | null;
  declare greeting: string | null;
  declare placeholder: string | null;
  declare storage: string | null;
  declare identity: string | null;
  declare isOpen: boolean;
  declare config: WidgetPublicConfig | null;
  declare configFailed: boolean;
  declare draft: string;
  declare expanded: ReadonlySet<string>;

  private controller: ChatController | null = null;
  private started = false;
  private view: View;
  private restoreFocus = false;
  private messageCount = 0;

  constructor() {
    super();
    this.widgetKey = null;
    this.apiBase = null;
    this.mode = null;
    this.position = null;
    this.theme = null;
    this.primaryColor = null;
    this.chatTitle = null;
    this.greeting = null;
    this.placeholder = null;
    this.storage = null;
    this.identity = null;
    this.isOpen = false;
    this.config = null;
    this.configFailed = false;
    this.draft = "";
    this.expanded = new Set();
    this.view = resolveView(this, null);
  }

  override connectedCallback(): void {
    super.connectedCallback();
    // Moving the element in the page reconnects it; the conversation goes on.
    if (!this.started) void this.start();
  }

  override disconnectedCallback(): void {
    super.disconnectedCallback();
    this.controller?.abort();
  }

  private emit(name: string, detail: Record<string, unknown>): void {
    this.dispatchEvent(new CustomEvent(name, { detail, bubbles: true, composed: true }));
  }

  private async start(): Promise<void> {
    this.started = true;
    const key = this.widgetKey;
    if (!isWidgetKey(key)) {
      this.emit("knobridge-error", { code: "widget_key_missing", status: null });
      return;
    }
    const api = new WidgetApi(apiOrigin(this.apiBase) ?? scriptOrigin ?? location.origin, key);
    const store = new ConversationStore(pick(this.storage, STORAGES, "storage") ?? "local", key);
    const host = {
      emit: (name: string, detail: Record<string, unknown>) => {
        this.emit(name, detail);
      },
      changed: () => {
        this.requestUpdate();
      },
    };
    // Read on each use, so setIdentity() applies to the next conversation.
    this.controller = new ChatController(api, store, host, () => this.identity ?? null);
    try {
      this.config = await api.config();
    } catch (error) {
      const apiError = asApiError(error);
      this.configFailed = true;
      this.emit("knobridge-error", { code: apiError.code, status: apiError.status });
      return;
    }
    this.emit("knobridge-ready", {
      mode: resolveView(this, this.config).mode,
      ticketEnabled: this.config.ticket_enabled,
      feedbackEnabled: this.config.feedback_enabled,
    });
    await this.controller.restore();
  }

  // Public methods (docs/specs/widget.md, "Métodos").

  open(): void {
    if (this.view.mode === "bubble") this.isOpen = true;
  }

  close(): void {
    if (this.view.mode !== "bubble" || !this.isOpen) return;
    // Esc or "Fechar" from inside the panel gives the focus back to the launcher.
    this.restoreFocus = this.shadowRoot?.activeElement != null;
    this.isOpen = false;
  }

  toggle(): void {
    if (this.isOpen) this.close();
    else this.open();
  }

  /** Same as changing the attribute; with another `sub`, the next question opens a conversation. */
  setIdentity(identity: string | null): void {
    this.identity = identity;
  }

  newConversation(): void {
    this.controller?.reset();
    this.draft = "";
    this.expanded = new Set();
    this.focusInput();
  }

  // Lifecycle.

  protected override willUpdate(changed: PropertyValues<this>): void {
    if (APPEARANCE.some((name) => changed.has(name))) this.view = resolveView(this, this.config);
  }

  protected override updated(changed: PropertyValues<this>): void {
    if (changed.has("identity") && changed.get("identity") !== undefined) {
      void this.controller?.identityChanged();
    }
    if (changed.has("isOpen") && changed.get("isOpen") !== undefined) {
      if (this.isOpen) {
        this.emit("knobridge-open", {});
        this.focusInput();
      } else {
        this.emit("knobridge-close", {});
        if (this.restoreFocus) this.shadowRoot?.querySelector<HTMLElement>(".launcher")?.focus();
        this.restoreFocus = false;
      }
    }
    const count = this.controller?.messages.length ?? 0;
    if (count !== this.messageCount) {
      this.messageCount = count;
      for (const log of this.renderRoot.querySelectorAll(".messages")) {
        log.scrollTop = log.scrollHeight;
      }
    }
  }

  private focusInput(): void {
    void this.updateComplete.then(() => {
      this.shadowRoot?.querySelector("textarea")?.focus();
    });
  }

  // Handlers.

  private submit(): void {
    const question = this.draft.trim();
    const controller = this.controller;
    if (!controller || controller.busy || !question || question.length > this.view.maxChars) {
      return;
    }
    this.draft = "";
    void controller.send(question);
  }

  private readonly onSubmit = (event: Event) => {
    event.preventDefault();
    this.submit();
  };

  private readonly onInput = (event: Event) => {
    this.draft = (event.target as HTMLTextAreaElement).value;
  };

  private readonly onInputKeydown = (event: KeyboardEvent) => {
    if (event.key !== "Enter" || event.shiftKey || event.isComposing) return;
    event.preventDefault();
    this.submit();
  };

  private readonly onNewConversation = () => {
    this.newConversation();
  };

  private readonly onClose = () => {
    this.close();
  };

  private readonly onToggle = () => {
    this.toggle();
  };

  private readonly onPanelKeydown = (event: KeyboardEvent) => {
    if (event.key !== "Escape" || this.view.mode !== "bubble") return;
    event.stopPropagation();
    this.close();
  };

  private toggleCitation(messageKey: string, index: number, force?: boolean): void {
    const id = `${messageKey}:${String(index)}`;
    const next = new Set(this.expanded);
    if (force ?? !next.has(id)) next.add(id);
    else next.delete(id);
    this.expanded = next;
  }

  // Rendering.

  private focusById(id: string): void {
    void this.updateComplete.then(() => {
      this.shadowRoot?.getElementById(id)?.focus();
    });
  }

  private context(
    t: Translate,
    controller: ChatController,
    config: WidgetPublicConfig,
  ): MessageContext {
    // Under each finished answer: feedback and "Abrir chamado", as the configuration allows.
    const actions: ActionsContext = {
      t,
      actions: controller.actions,
      feedbackEnabled: config.feedback_enabled,
      // The conversation (and each `done`) may say the product lost its webhook since loading.
      ticketEnabled: config.ticket_enabled && controller.ticketEnabled !== false,
      focus: (id) => {
        this.focusById(id);
      },
    };
    return {
      t,
      isExpanded: (messageKey, index) => this.expanded.has(`${messageKey}:${String(index)}`),
      toggleCitation: (messageKey, index) => {
        this.toggleCitation(messageKey, index);
      },
      showCitation: (messageKey, index) => {
        this.toggleCitation(messageKey, index, true);
        this.focusById(citationId(messageKey, index));
      },
      retry: (messageKey) => {
        void controller.retry(messageKey);
      },
      answerActions: (message) => renderAnswerActions(message, actions),
    };
  }

  private renderPanel(
    t: Translate,
    controller: ChatController,
    config: WidgetPublicConfig,
  ): TemplateResult {
    const view = this.view;
    const bubble = view.mode === "bubble";
    const ctx = this.context(t, controller, config);
    return html`<section
      part="panel"
      class="panel"
      id="panel"
      role="dialog"
      aria-modal="false"
      aria-labelledby="title"
      ?hidden=${bubble && !this.isOpen}
      @keydown=${this.onPanelKeydown}
    >
      <header part="header">
        <h2 id="title">${view.title}</h2>
        <button type="button" @click=${this.onNewConversation}>${t("newConversation")}</button>
        ${
          bubble
            ? html`<button type="button" @click=${this.onClose}>${t("close")}</button>`
            : nothing
        }
      </header>
      <div part="messages" class="messages" role="log" aria-live="polite">
        ${renderGreeting(view.greeting, ctx)}
        ${controller.messages.map((message) => renderMessage(message, ctx))}
      </div>
      ${renderComposer({
        t,
        draft: this.draft,
        placeholder: view.placeholder,
        maxChars: view.maxChars,
        busy: controller.busy,
        onSubmit: this.onSubmit,
        onInput: this.onInput,
        onKeydown: this.onInputKeydown,
      })}
    </section>`;
  }

  protected override render(): TemplateResult | typeof nothing {
    const controller = this.controller;
    if (!controller) return nothing;
    const view = this.view;
    const t = translator(this.lang || this.config?.language);
    const classes = [
      "root",
      view.mode,
      view.theme,
      view.position === "bottom-left" ? "left" : "right",
    ].join(" ");
    const style = styleMap({
      "--kb-primary": view.primary,
      "--kb-primary-contrast": contrastColor(view.primary),
    });
    if (!this.config) {
      // No configuration: the bubble shows nothing; the inline mode says the chat is unavailable.
      return this.configFailed && view.mode === "inline"
        ? html`<div class=${classes} style=${style}>
            <div part="panel" class="panel" role="status">${t("unavailable")}</div>
          </div>`
        : nothing;
    }
    const open = this.isOpen;
    return html`<div class=${classes} style=${style}>
      ${
        view.mode === "bubble"
          ? html`<button
              part="launcher"
              class="launcher"
              type="button"
              aria-label=${t(open ? "launcherClose" : "launcherOpen")}
              aria-expanded=${open ? "true" : "false"}
              aria-controls="panel"
              @click=${this.onToggle}
            >
              ${open ? CLOSE_ICON : CHAT_ICON}
            </button>`
          : nothing
      }
      ${this.renderPanel(t, controller, this.config)}
    </div>`;
  }
}
