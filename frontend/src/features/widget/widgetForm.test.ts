import { describe, expect, it } from "vitest";

import { i18n } from "@/i18n";
import { PRODUCT_ID } from "@/test/factories";
import { makeWidget } from "@/test/widgetFactories";

import {
  originIssuesText,
  toWidgetChanges,
  toWidgetInput,
  widgetFormDefaults,
  widgetFormSchema,
  type WidgetFormValues,
} from "./widgetForm";

const schema = widgetFormSchema(i18n.t);

function values(overrides: Partial<WidgetFormValues> = {}): WidgetFormValues {
  return {
    ...widgetFormDefaults(undefined, PRODUCT_ID),
    name: "Site",
    origins: "https://app.cliente.com.br",
    ...overrides,
  };
}

function messages(input: WidgetFormValues): string[] {
  const result = schema.safeParse(input);
  return result.success ? [] : result.error.issues.map(({ message }) => message);
}

describe("widgetFormSchema", () => {
  it("test_widget_form_accepts_the_defaults_with_name_and_origin", () => {
    expect(messages(values())).toEqual([]);
  });

  it.each<[Partial<WidgetFormValues>, string]>([
    [{ productId: "" }, "Escolha o produto do widget."],
    [{ name: "  " }, "Informe o nome do widget."],
    [{ name: "a".repeat(201) }, "Use no máximo 200 caracteres."],
    [{ origins: "\n" }, "Informe ao menos uma origem."],
    [{ primaryColor: "blue" }, "Use uma cor no formato #RRGGBB."],
    [{ title: "a".repeat(81) }, "Use no máximo 80 caracteres."],
    [{ greeting: "a".repeat(501) }, "Use no máximo 500 caracteres."],
    [{ placeholder: "a".repeat(121) }, "Use no máximo 120 caracteres."],
    [{ messagesPerIpPerHour: "0" }, "Use um número inteiro de 1 a 1000."],
    [{ messagesPerIpPerHour: "2.5" }, "Use um número inteiro de 1 a 1000."],
    [{ messagesPerDay: "100001" }, "Use um número inteiro de 1 a 100000."],
  ])("test_widget_form_refuses_%o", (overrides, message) => {
    expect(messages(values(overrides))).toEqual([message]);
  });

  it("test_widget_form_refuses_more_than_fifty_origins", () => {
    const origins = Array.from({ length: 51 }, (_, index) => `https://s${String(index)}.com`);

    expect(messages(values({ origins: origins.join("\n") }))).toEqual([
      "Use no máximo 50 origens.",
    ]);
  });

  it("test_widget_form_names_each_refused_origin_and_why", () => {
    expect(messages(values({ origins: "https://a.com/app\nftp://b.com" }))).toEqual([
      "https://a.com/app: tire o caminho, a consulta e a barra final. ftp://b.com: use http ou https.",
    ]);
  });
});

describe("originIssuesText", () => {
  it("test_origin_issues_text_falls_back_for_an_unknown_reason", () => {
    expect(originIssuesText([{ origin: "x", reason: "other" }], i18n.t)).toBe(
      "x: não é uma origem válida (esquema://domínio[:porta]).",
    );
  });
});

describe("widget form bodies", () => {
  it("test_widget_form_defaults_of_a_widget", () => {
    const form = widgetFormDefaults(makeWidget({ title: "Ajuda" }));

    expect(form.origins).toBe("https://app.cliente.com.br\nhttps://*.cliente.com.br");
    expect(form.title).toBe("Ajuda");
    expect(form.messagesPerDay).toBe("1000");
    expect(widgetFormDefaults(makeWidget()).title).toBe("");
  });

  it("test_to_widget_input_converts_the_typed_values", () => {
    expect(
      toWidgetInput(
        values({
          name: " Site ",
          origins: "https://a.com\n\nhttps://b.com",
          primaryColor: "#AABBCC",
          title: "  ",
          messagesPerIpPerHour: " 10 ",
        }),
      ),
    ).toEqual({
      product_id: PRODUCT_ID,
      name: "Site",
      allowed_origins: ["https://a.com", "https://b.com"],
      active: true,
      mode: "bubble",
      position: "bottom-right",
      theme: "auto",
      primary_color: "#aabbcc",
      title: null,
      greeting: "Olá! Como posso ajudar?",
      placeholder: "Escreva sua pergunta",
      feedback_enabled: true,
      ticket_enabled: true,
      messages_per_ip_per_hour: 10,
      messages_per_day: 1000,
    });
  });

  it("test_to_widget_changes_sends_only_what_changed", () => {
    const widget = makeWidget();
    const form = widgetFormDefaults(widget);

    expect(toWidgetChanges(widget, form)).toBeNull();
    expect(
      toWidgetChanges(widget, {
        ...form,
        title: "Ajuda",
        origins: "https://app.cliente.com.br",
        mode: "inline",
      }),
    ).toEqual({ title: "Ajuda", allowed_origins: ["https://app.cliente.com.br"], mode: "inline" });
  });

  it("test_to_widget_changes_clears_the_title_with_null", () => {
    const widget = makeWidget({ title: "Ajuda" });

    expect(toWidgetChanges(widget, { ...widgetFormDefaults(widget), title: "" })).toEqual({
      title: null,
    });
  });
});
