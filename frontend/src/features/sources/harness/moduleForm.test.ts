import { describe, expect, it } from "vitest";

import { i18n } from "@/i18n";
import { makeHarnessModule } from "@/test/harnessFactories";

import {
  isValidPattern,
  moduleCreateBody,
  moduleFormSchema,
  moduleFormValues,
  moduleUpdateBody,
  parsePatterns,
} from "./moduleForm";

const t = i18n.t.bind(i18n);

describe("parsePatterns", () => {
  it("test_parse_patterns_trims_and_drops_blank_lines", () => {
    expect(parsePatterns(" src/** \n\n !src/x/**\n")).toEqual(["src/**", "!src/x/**"]);
  });
});

describe("isValidPattern", () => {
  it.each(["src/**", "!src/a/**", "docs/", "*", "src/[ab]?.py"])(
    "test_is_valid_pattern_accepts_%s",
    (pattern) => {
      expect(isValidPattern(pattern)).toBe(true);
    },
  );

  it.each([
    "/abs/**",
    "C:/src",
    "src\\a",
    "../fora",
    "src/./a",
    "src//a",
    "!",
    "a\u0007b",
    "a".repeat(301),
  ])("test_is_valid_pattern_refuses_%s", (pattern) => {
    expect(isValidPattern(pattern)).toBe(false);
  });
});

describe("module bodies", () => {
  it("test_module_form_values_of_a_module_and_of_a_new_one", () => {
    expect(moduleFormValues()).toEqual({ title: "", key: "", paths: "", enabled: true });
    expect(
      moduleFormValues(makeHarnessModule({ paths: ["a/**", "!a/b/**"], enabled: false })),
    ).toEqual({
      title: "src/faturamento",
      key: "src-faturamento",
      paths: "a/**\n!a/b/**",
      enabled: false,
    });
  });

  it("test_module_create_body_sends_the_key_only_when_typed", () => {
    const values = { title: " Notas ", key: " notas ", paths: "src/notas/**", enabled: true };

    expect(moduleCreateBody(values)).toEqual({
      title: "Notas",
      key: "notas",
      paths: ["src/notas/**"],
      enabled: true,
    });
    expect(moduleCreateBody({ ...values, key: "  " })).toEqual({
      title: "Notas",
      paths: ["src/notas/**"],
      enabled: true,
    });
  });

  it("test_module_update_body_never_sends_the_key", () => {
    expect(
      moduleUpdateBody({ title: "Notas", key: "outra", paths: "a/**\nb/**", enabled: false }),
    ).toEqual({ title: "Notas", paths: ["a/**", "b/**"], enabled: false });
  });
});

describe("moduleFormSchema", () => {
  it("test_module_form_schema_ignores_the_key_when_editing", () => {
    const schema = moduleFormSchema(t, { creating: false });

    expect(
      schema.safeParse({ title: "x", key: "Qualquer Coisa", paths: "a/**", enabled: true }).success,
    ).toBe(true);
  });

  it("test_module_form_schema_limits_title_and_key", () => {
    const schema = moduleFormSchema(t, { creating: true });

    expect(
      schema.safeParse({ title: "a".repeat(201), key: "", paths: "a/**", enabled: true }).success,
    ).toBe(false);
    expect(
      schema.safeParse({ title: "a", key: "a".repeat(101), paths: "a/**", enabled: true }).success,
    ).toBe(false);
    expect(
      schema.safeParse({ title: "a", key: "notas-fiscais", paths: "a/**", enabled: true }).success,
    ).toBe(true);
  });
});
