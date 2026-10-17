import { describe, expect, it } from "vitest";

import { i18n } from "@/i18n";
import { PROVIDER_ID } from "@/test/factories";
import { makeUnconfiguredLevel, makeWorkspaceLevel } from "@/test/levelFactories";

import {
  isDefaultInstructions,
  LEVEL_INSTRUCTIONS_MAX_LENGTH,
  levelBody,
  levelFormDefaults,
  levelFormSchema,
  type LevelFormValues,
  NO_PROVIDER,
  parseTemperature,
} from "./levelForm";

const t = i18n.t.bind(i18n);

/** The form of the default level (`end_user`, configured) with `overrides`. */
function form(overrides: Partial<LevelFormValues> = {}): LevelFormValues {
  return { ...levelFormDefaults(makeWorkspaceLevel()), ...overrides };
}

function errorsOf(input: LevelFormValues): Record<string, string> {
  const result = levelFormSchema(t).safeParse(input);
  return result.success
    ? {}
    : Object.fromEntries(result.error.issues.map((issue) => [issue.path.join("."), issue.message]));
}

describe("levelForm", () => {
  it("test_level_form_defaults_read_the_stored_level", () => {
    expect(levelFormDefaults(makeWorkspaceLevel())).toEqual({
      providerId: PROVIDER_ID,
      model: "gpt-4.1-mini",
      temperature: "0.2",
      instructions: "Você atende o usuário final. Nunca mostre código.",
      maxSteps: "2",
    });
    expect(levelFormDefaults(makeUnconfiguredLevel("support"))).toMatchObject({
      providerId: NO_PROVIDER,
      model: "",
    });
  });

  it("test_parse_temperature_accepts_comma_or_dot_from_0_to_2", () => {
    expect(parseTemperature("0,7")).toBe(0.7);
    expect(parseTemperature(" 1.5 ")).toBe(1.5);
    expect(parseTemperature("2")).toBe(2);
    expect(parseTemperature("2.1")).toBeNull();
    expect(parseTemperature("-1")).toBeNull();
    expect(parseTemperature("abc")).toBeNull();
  });

  it("test_level_body_sends_default_instructions_as_null", () => {
    const level = makeWorkspaceLevel();

    expect(levelBody(form({ instructions: `${level.default_instructions}\n` }), level)).toEqual({
      provider_id: PROVIDER_ID,
      model: "gpt-4.1-mini",
      temperature: 0.2,
      instructions: null,
      max_steps: 2,
    });
  });

  it("test_level_body_sends_the_chosen_max_steps", () => {
    expect(levelBody(form({ maxSteps: "6" }), makeWorkspaceLevel()).max_steps).toBe(6);
  });

  it("test_level_form_accepts_max_steps_from_1_to_6", () => {
    expect(errorsOf(form({ maxSteps: "1" }))).toEqual({});
    expect(errorsOf(form({ maxSteps: "6" }))).toEqual({});
    expect(errorsOf(form({ maxSteps: "7" }))).toEqual({ maxSteps: "Escolha de 1 a 6 buscas." });
    expect(errorsOf(form({ maxSteps: "0" }))).toEqual({ maxSteps: "Escolha de 1 a 6 buscas." });
  });

  it("test_level_body_sends_edited_instructions_and_parsed_temperature", () => {
    const body = levelBody(
      form({ instructions: "Outro texto.", temperature: "0,9" }),
      makeWorkspaceLevel(),
    );

    expect(body.instructions).toBe("Outro texto.");
    expect(body.temperature).toBe(0.9);
  });

  it("test_level_body_without_credential_turns_the_level_off", () => {
    const level = makeWorkspaceLevel({ temperature: 0.4 });
    const body = levelBody(form({ providerId: NO_PROVIDER, model: "", temperature: "x" }), level);

    expect(body).toMatchObject({ provider_id: null, model: null, temperature: 0.4 });
  });

  it("test_is_default_instructions_ignores_blank_ends", () => {
    const level = makeWorkspaceLevel();

    expect(isDefaultInstructions(level, `  ${level.default_instructions}  `)).toBe(true);
    expect(isDefaultInstructions(level, "outro")).toBe(false);
  });

  it("test_level_form_schema_requires_credential_and_model_together", () => {
    expect(errorsOf(form({ model: "" }))).toEqual({
      model: "Informe o modelo junto com a credencial.",
    });
    expect(errorsOf(form({ providerId: NO_PROVIDER }))).toEqual({
      providerId: "Escolha a credencial junto com o modelo.",
    });
    expect(errorsOf(form({ providerId: NO_PROVIDER, model: "" }))).toEqual({});
  });

  it("test_level_form_schema_checks_model_temperature_and_length", () => {
    expect(errorsOf(form({ model: "gpt 4" }))).toEqual({
      model: "O identificador do modelo não pode ter espaços.",
    });
    expect(errorsOf(form({ temperature: "3" }))).toEqual({
      temperature: "Informe um número de 0 a 2.",
    });
    expect(
      Object.keys(errorsOf(form({ instructions: "a".repeat(LEVEL_INSTRUCTIONS_MAX_LENGTH + 1) }))),
    ).toEqual(["instructions"]);
  });
});
