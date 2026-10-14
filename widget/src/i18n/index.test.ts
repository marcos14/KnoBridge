import { describe, expect, it } from "vitest";

import { format, messagesFor, translator } from "./index.ts";
import { ptBR } from "./pt-BR.ts";

describe("i18n", () => {
  it("test_messages_for_falls_back_to_pt_br", () => {
    expect(messagesFor("pt-BR")).toBe(ptBR);
    expect(messagesFor("en")).toBe(ptBR);
    expect(messagesFor(null)).toBe(ptBR);
    expect(messagesFor("")).toBe(ptBR);
  });

  it("test_format_replaces_known_placeholders_only", () => {
    expect(format("{count} de {max} {other}", { count: 3, max: "10" })).toBe("3 de 10 {other}");
  });

  it("test_translator_formats_with_params", () => {
    const t = translator("pt-BR");

    expect(t("send")).toBe("Enviar");
    expect(t("sourceLabel", { n: 2, title: "a.md" })).toBe("Fonte 2: a.md");
  });
});
