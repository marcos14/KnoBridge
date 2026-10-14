import { ptBR, type MessageKey, type Messages } from "./pt-BR.ts";

export type { MessageKey, Messages };

const CATALOGS: Readonly<Record<string, Messages>> = { "pt-BR": ptBR };

/** The catalog of `lang`; unknown languages fall back to pt-BR. */
export function messagesFor(lang: string | null | undefined): Messages {
  return (lang ? CATALOGS[lang] : undefined) ?? ptBR;
}

/** Replaces `{name}` placeholders; unknown placeholders stay as written. */
export function format(
  template: string,
  params: Readonly<Record<string, string | number>>,
): string {
  return template.replace(/\{(\w+)\}/g, (whole, name: string) =>
    name in params ? String(params[name]) : whole,
  );
}

export type Translate = (
  key: MessageKey,
  params?: Readonly<Record<string, string | number>>,
) => string;

export function translator(lang: string | null | undefined): Translate {
  const messages = messagesFor(lang);
  return (key, params) => (params ? format(messages[key], params) : messages[key]);
}
