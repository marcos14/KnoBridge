// The question field (docs/specs/widget.md, "Acessibilidade"): a labelled <textarea> with the
// character counter tied by aria-describedby. Enter sends and Shift+Enter breaks the line (the
// element handles the keys); while an answer streams the field is read-only, keeping the focus.

import { html, type TemplateResult } from "lit";

import type { Translate } from "../i18n/index.ts";

export interface ComposerProps {
  t: Translate;
  draft: string;
  placeholder: string;
  maxChars: number;
  busy: boolean;
  onSubmit: (event: Event) => void;
  onInput: (event: Event) => void;
  onKeydown: (event: KeyboardEvent) => void;
}

export function renderComposer(props: ComposerProps): TemplateResult {
  const { t, busy, maxChars } = props;
  const length = props.draft.trim().length;
  const over = length > maxChars;
  return html`<form part="composer" @submit=${props.onSubmit}>
    <label class="sr-only" for="input">${t("inputLabel")}</label>
    <textarea
      part="input"
      id="input"
      rows="2"
      .value=${props.draft}
      placeholder=${props.placeholder}
      aria-describedby="counter"
      ?readonly=${busy}
      aria-disabled=${busy ? "true" : "false"}
      @input=${props.onInput}
      @keydown=${props.onKeydown}
    ></textarea>
    <span id="counter" class=${over ? "counter over" : "counter"}>
      ${over ? t("tooLong", { max: maxChars }) : t("counter", { count: length, max: maxChars })}
    </span>
    <button part="send" class="send" type="submit" ?disabled=${busy || !length || over}>
      ${t("send")}
    </button>
  </form>`;
}
