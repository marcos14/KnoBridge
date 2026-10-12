import { describe, expect, it } from "vitest";

import { i18n } from "@/i18n";
import { makeProvider } from "@/test/factories";

import { createBody, providerFormDefaults, providerFormSchema, updateBody } from "./providerForm";

const t = i18n.t.bind(i18n);

describe("providerForm", () => {
  it("test_provider_form_defaults_never_carry_a_key", () => {
    const provider = makeProvider({ base_url: "https://proxy.test" });

    expect(providerFormDefaults(provider)).toEqual({
      kind: "openai",
      name: "OpenAI Produção",
      baseUrl: "https://proxy.test",
      apiKey: "",
    });
    expect(providerFormDefaults()).toEqual({ kind: "openai", name: "", baseUrl: "", apiKey: "" });
  });

  it("test_provider_form_create_body_leaves_blank_base_url_out", () => {
    const values = { kind: "anthropic" as const, name: "A", baseUrl: "", apiKey: "sk-12345678" };

    expect(createBody(values)).toEqual({ kind: "anthropic", name: "A", api_key: "sk-12345678" });
  });

  it("test_provider_form_update_body_clears_base_url_and_keeps_key", () => {
    expect(updateBody({ kind: "openai", name: "A", baseUrl: "", apiKey: "" })).toEqual({
      name: "A",
      base_url: null,
    });
  });

  it("test_provider_form_schema_key_optional_only_when_editing", () => {
    const values = { kind: "openai", name: "A", baseUrl: "", apiKey: "" };

    expect(providerFormSchema(t, true).safeParse(values).success).toBe(true);
    expect(providerFormSchema(t, false).safeParse(values).success).toBe(false);
  });

  it("test_provider_form_schema_limits_lengths", () => {
    const result = providerFormSchema(t, false).safeParse({
      kind: "openai",
      name: "n".repeat(201),
      baseUrl: `https://x.test/${"a".repeat(500)}`,
      apiKey: "k".repeat(4097),
    });

    expect(result.error?.issues.map((issue) => issue.message)).toEqual([
      "Use no máximo 200 caracteres.",
      "Use no máximo 500 caracteres.",
      "Use no máximo 4096 caracteres.",
    ]);
  });
});
