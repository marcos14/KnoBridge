import { describe, expect, it } from "vitest";

import { i18n } from "@/i18n";
import { COLLECTION_ID, makeAssistant, OTHER_COLLECTION_ID, PROVIDER_ID } from "@/test/factories";

import {
  assistantBody,
  assistantFormDefaults,
  assistantFormSchema,
  DEFAULT_MIN_SIMILARITY,
  DEFAULT_TEMPERATURE,
  parseMinSimilarity,
  parseTemperature,
} from "./assistantForm";

const t = i18n.t.bind(i18n);

describe("parseTemperature", () => {
  it.each([
    ["0", 0],
    ["0.7", 0.7],
    [" 1,5 ", 1.5],
    ["2", 2],
  ])("test_parse_temperature_accepts_%s", (text, value) => {
    expect(parseTemperature(text)).toBe(value);
  });

  it.each(["", "abc", "-0.1", "2.1", "1e1", "1.", ".5"])(
    "test_parse_temperature_rejects_%s",
    (text) => {
      expect(parseTemperature(text)).toBeNull();
    },
  );
});

describe("parseMinSimilarity", () => {
  it.each([
    ["0", 0],
    ["0,3", 0.3],
    [" 1 ", 1],
  ])("test_parse_min_similarity_accepts_%s", (text, value) => {
    expect(parseMinSimilarity(text)).toBe(value);
  });

  it.each(["", "abc", "-0.1", "1.1", ".5"])("test_parse_min_similarity_rejects_%s", (text) => {
    expect(parseMinSimilarity(text)).toBeNull();
  });
});

describe("assistantForm", () => {
  it("test_assistant_form_defaults_follow_the_contract", () => {
    expect(assistantFormDefaults(undefined, PROVIDER_ID)).toEqual({
      name: "",
      description: "",
      systemPrompt: "",
      providerId: PROVIDER_ID,
      model: "",
      temperature: "0.2",
      language: "pt-BR",
      tone: "neutral",
      noSourceMessage: "",
      active: true,
      collectionIds: [],
      minSimilarity: "0.3",
    });
  });

  it("test_assistant_form_round_trips_an_assistant", () => {
    const assistant = makeAssistant({
      temperature: 1.1,
      active: false,
      collection_ids: [COLLECTION_ID, OTHER_COLLECTION_ID],
      min_similarity: 0.55,
    });

    expect(assistantBody(assistantFormDefaults(assistant, ""))).toEqual({
      name: assistant.name,
      description: assistant.description,
      system_prompt: assistant.system_prompt,
      provider_id: assistant.provider_id,
      model: assistant.model,
      temperature: 1.1,
      language: assistant.language,
      tone: assistant.tone,
      no_source_message: assistant.no_source_message,
      active: false,
      collection_ids: [COLLECTION_ID, OTHER_COLLECTION_ID],
      min_similarity: 0.55,
    });
  });

  it("test_assistant_body_falls_back_to_default_temperature", () => {
    const values = { ...assistantFormDefaults(undefined, PROVIDER_ID), temperature: "x" };

    expect(assistantBody(values).temperature).toBe(DEFAULT_TEMPERATURE);
  });

  it("test_assistant_body_reads_min_similarity_with_comma_or_falls_back", () => {
    const values = assistantFormDefaults(undefined, PROVIDER_ID);

    expect(assistantBody({ ...values, minSimilarity: "0,45" }).min_similarity).toBe(0.45);
    expect(assistantBody({ ...values, minSimilarity: "x" }).min_similarity).toBe(
      DEFAULT_MIN_SIMILARITY,
    );
  });

  it("test_assistant_form_schema_rejects_min_similarity_out_of_range", () => {
    const values = {
      ...assistantFormDefaults(undefined, PROVIDER_ID),
      name: "Ok",
      model: "m",
      minSimilarity: "1.5",
    };

    const result = assistantFormSchema(t).safeParse(values);

    expect(result.error?.issues.map((issue) => issue.message)).toEqual([
      "Informe um número de 0 a 1.",
    ]);
  });

  it("test_assistant_form_schema_limits_lengths", () => {
    const values = {
      ...assistantFormDefaults(undefined, PROVIDER_ID),
      name: "Ok",
      model: "m",
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

  it("test_assistant_form_schema_requires_provider", () => {
    const values = { ...assistantFormDefaults(undefined, ""), name: "Ok", model: "m" };

    const result = assistantFormSchema(t).safeParse(values);

    expect(result.error?.issues.map((issue) => issue.message)).toEqual(["Escolha um provedor."]);
  });
});
