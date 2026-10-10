import { describe, expect, it } from "vitest";

import { i18n } from "@/i18n";
import { makeAssistant, PROVIDER_ID } from "@/test/factories";

import {
  assistantBody,
  assistantFormDefaults,
  assistantFormSchema,
  DEFAULT_TEMPERATURE,
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
    });
  });

  it("test_assistant_form_round_trips_an_assistant", () => {
    const assistant = makeAssistant({ temperature: 1.1, active: false });

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
    });
  });

  it("test_assistant_body_falls_back_to_default_temperature", () => {
    const values = { ...assistantFormDefaults(undefined, PROVIDER_ID), temperature: "x" };

    expect(assistantBody(values).temperature).toBe(DEFAULT_TEMPERATURE);
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
