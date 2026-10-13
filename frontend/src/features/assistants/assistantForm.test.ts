import { describe, expect, it } from "vitest";

import { i18n } from "@/i18n";
import { COLLECTION_ID, makeAssistant, OTHER_COLLECTION_ID } from "@/test/factories";

import {
  assistantBody,
  assistantFormDefaults,
  assistantFormSchema,
  DEFAULT_MIN_SIMILARITY,
  parseMinSimilarity,
} from "./assistantForm";

const t = i18n.t.bind(i18n);

describe("parseMinSimilarity", () => {
  it.each([
    ["0", 0],
    ["0,3", 0.3],
    [" 1 ", 1],
  ])("test_parse_min_similarity_accepts_%s", (text, value) => {
    expect(parseMinSimilarity(text)).toBe(value);
  });

  it.each(["", "abc", "-0.1", "1.1", ".5", "1e1", "1."])(
    "test_parse_min_similarity_rejects_%s",
    (text) => {
      expect(parseMinSimilarity(text)).toBeNull();
    },
  );
});

describe("assistantForm", () => {
  it("test_assistant_form_defaults_follow_the_contract", () => {
    expect(assistantFormDefaults(undefined)).toEqual({
      name: "",
      description: "",
      systemPrompt: "",
      language: "pt-BR",
      tone: "neutral",
      noSourceMessage: "",
      active: true,
      collectionIds: [],
      minSimilarity: "0.35",
      ticketWebhookEnabled: false,
      ticketWebhookUrl: "",
    });
  });

  it("test_assistant_form_round_trips_an_assistant", () => {
    const assistant = makeAssistant({
      active: false,
      collection_ids: [COLLECTION_ID, OTHER_COLLECTION_ID],
      min_similarity: 0.55,
    });

    expect(assistantBody(assistantFormDefaults(assistant))).toEqual({
      name: assistant.name,
      description: assistant.description,
      instructions: assistant.instructions,
      language: assistant.language,
      tone: assistant.tone,
      no_source_message: assistant.no_source_message,
      active: false,
      collection_ids: [COLLECTION_ID, OTHER_COLLECTION_ID],
      min_similarity: 0.55,
      ticket_webhook_url: null,
    });
  });

  it("test_assistant_form_reads_the_webhook_of_an_assistant", () => {
    const assistant = makeAssistant({ ticket_webhook_url: "https://chamados.example.test/kb" });

    const values = assistantFormDefaults(assistant);

    expect([values.ticketWebhookEnabled, values.ticketWebhookUrl]).toEqual([
      true,
      "https://chamados.example.test/kb",
    ]);
  });

  it("test_assistant_body_leaves_an_unchanged_webhook_out_of_the_patch", () => {
    const assistant = makeAssistant({ ticket_webhook_url: "https://chamados.example.test/kb" });
    const values = assistantFormDefaults(assistant);

    expect(assistantBody(values, assistant)).not.toHaveProperty("ticket_webhook_url");
    expect(
      assistantBody({ ...values, ticketWebhookUrl: "https://novo.example.test/kb" }, assistant),
    ).toHaveProperty("ticket_webhook_url", "https://novo.example.test/kb");
    expect(assistantBody({ ...values, ticketWebhookEnabled: false }, assistant)).toHaveProperty(
      "ticket_webhook_url",
      null,
    );
  });

  it.each([
    ["", "Informe a URL do webhook."],
    ["chamados.example.test", "Informe uma URL http ou https válida, sem usuário e senha."],
  ])("test_assistant_form_schema_checks_the_webhook_url_%s", (url, message) => {
    const values = {
      ...assistantFormDefaults(undefined),
      name: "Ok",
      ticketWebhookEnabled: true,
      ticketWebhookUrl: url,
    };

    const result = assistantFormSchema(t).safeParse(values);

    expect(result.error?.issues.map((issue) => [issue.path, issue.message])).toEqual([
      [["ticketWebhookUrl"], message],
    ]);
  });

  it("test_assistant_form_schema_ignores_the_url_with_the_webhook_off", () => {
    const values = {
      ...assistantFormDefaults(undefined),
      name: "Ok",
      ticketWebhookUrl: "não é url",
    };

    expect(assistantFormSchema(t).safeParse(values).success).toBe(true);
  });

  it("test_assistant_form_schema_accepts_a_webhook_url", () => {
    const values = {
      ...assistantFormDefaults(undefined),
      name: "Ok",
      ticketWebhookEnabled: true,
      ticketWebhookUrl: " https://chamados.example.test/kb ",
    };

    const result = assistantFormSchema(t).safeParse(values);

    expect(result.data?.ticketWebhookUrl).toBe("https://chamados.example.test/kb");
  });

  it("test_assistant_body_reads_min_similarity_with_comma_or_falls_back", () => {
    const values = assistantFormDefaults(undefined);

    expect(assistantBody({ ...values, minSimilarity: "0,45" }).min_similarity).toBe(0.45);
    expect(assistantBody({ ...values, minSimilarity: "x" }).min_similarity).toBe(
      DEFAULT_MIN_SIMILARITY,
    );
  });

  it("test_assistant_form_schema_rejects_min_similarity_out_of_range", () => {
    const values = { ...assistantFormDefaults(undefined), name: "Ok", minSimilarity: "1.5" };

    const result = assistantFormSchema(t).safeParse(values);

    expect(result.error?.issues.map((issue) => issue.message)).toEqual([
      "Informe um número de 0 a 1.",
    ]);
  });

  it("test_assistant_form_schema_limits_lengths", () => {
    const values = {
      ...assistantFormDefaults(undefined),
      name: "Ok",
      description: "d".repeat(1001),
      systemPrompt: "s".repeat(20001),
      noSourceMessage: "n".repeat(2001),
    };

    const result = assistantFormSchema(t).safeParse(values);

    expect(result.error?.issues.map((issue) => issue.message)).toEqual([
      "Use no máximo 1000 caracteres.",
      "Use no máximo 20000 caracteres.",
      "Use no máximo 2000 caracteres.",
    ]);
  });

  it("test_assistant_form_schema_requires_a_name", () => {
    const result = assistantFormSchema(t).safeParse(assistantFormDefaults(undefined));

    expect(result.error?.issues.map((issue) => issue.path)).toEqual([["name"]]);
  });
});
