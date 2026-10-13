import type { TFunction } from "i18next";
import { describe, expect, it } from "vitest";

import { makeApiKey } from "@/test/apiKeyFactories";
import { PRODUCT_ID, OTHER_PRODUCT_ID } from "@/test/factories";

import {
  API_KEY_SCOPE_MAX,
  apiKeyFormDefaults,
  apiKeyFormSchema,
  toApiKeyChanges,
  toApiKeyInput,
} from "./apiKeyForm";

// Returns the key, so the assertions read which message was chosen.
const t = ((key: string) => key) as unknown as TFunction;

function issuesOf(values: unknown): string[] {
  const result = apiKeyFormSchema(t).safeParse(values);
  return result.success ? [] : result.error.issues.map((issue) => issue.message);
}

describe("apiKeyFormSchema", () => {
  it("test_api_key_form_schema_requires_a_name", () => {
    expect(issuesOf({ name: "  ", scope: "all", assistantIds: [] })).toEqual([
      "apiKeys.form.validation.nameRequired",
    ]);
  });

  it("test_api_key_form_schema_ignores_assistants_when_scope_is_all", () => {
    expect(issuesOf({ name: "portal", scope: "all", assistantIds: [] })).toEqual([]);
  });

  it("test_api_key_form_schema_requires_one_to_max_assistants_when_selected", () => {
    expect(issuesOf({ name: "portal", scope: "selected", assistantIds: [] })).toEqual([
      "apiKeys.form.validation.assistantsRequired",
    ]);
    const tooMany = Array.from({ length: API_KEY_SCOPE_MAX + 1 }, (_, index) => String(index));
    expect(issuesOf({ name: "portal", scope: "selected", assistantIds: tooMany })).toEqual([
      "apiKeys.form.validation.tooManyAssistants",
    ]);
    expect(issuesOf({ name: "portal", scope: "selected", assistantIds: [PRODUCT_ID] })).toEqual([]);
  });
});

describe("apiKeyFormDefaults", () => {
  it("test_api_key_form_defaults_of_a_new_key_cover_every_assistant", () => {
    expect(apiKeyFormDefaults()).toEqual({ name: "", scope: "all", assistantIds: [] });
  });

  it("test_api_key_form_defaults_read_the_scope_of_an_existing_key", () => {
    expect(apiKeyFormDefaults(makeApiKey())).toMatchObject({ scope: "all", assistantIds: [] });
    expect(apiKeyFormDefaults(makeApiKey({ assistant_ids: [PRODUCT_ID] }))).toEqual({
      name: "portal-cliente",
      scope: "selected",
      assistantIds: [PRODUCT_ID],
    });
  });
});

describe("toApiKeyInput", () => {
  it("test_to_api_key_input_trims_the_name_and_maps_the_scope", () => {
    expect(toApiKeyInput({ name: " portal ", scope: "all", assistantIds: [PRODUCT_ID] })).toEqual({
      name: "portal",
      assistant_ids: null,
    });
    expect(
      toApiKeyInput({ name: "portal", scope: "selected", assistantIds: [PRODUCT_ID] }),
    ).toEqual({ name: "portal", assistant_ids: [PRODUCT_ID] });
  });
});

describe("toApiKeyChanges", () => {
  const scoped = makeApiKey({ assistant_ids: [PRODUCT_ID, OTHER_PRODUCT_ID] });

  it("test_to_api_key_changes_is_null_when_nothing_changed", () => {
    expect(
      toApiKeyChanges(scoped, {
        name: " portal-cliente ",
        scope: "selected",
        assistantIds: [OTHER_PRODUCT_ID, PRODUCT_ID],
      }),
    ).toBeNull();
    expect(
      toApiKeyChanges(makeApiKey(), { name: "portal-cliente", scope: "all", assistantIds: [] }),
    ).toBeNull();
  });

  it("test_to_api_key_changes_sends_only_what_changed", () => {
    expect(
      toApiKeyChanges(scoped, {
        name: "portal",
        scope: "selected",
        assistantIds: [PRODUCT_ID, OTHER_PRODUCT_ID],
      }),
    ).toEqual({ name: "portal" });
    expect(
      toApiKeyChanges(scoped, {
        name: "portal-cliente",
        scope: "selected",
        assistantIds: [PRODUCT_ID],
      }),
    ).toEqual({ assistant_ids: [PRODUCT_ID] });
    expect(
      toApiKeyChanges(scoped, {
        name: "portal-cliente",
        scope: "selected",
        assistantIds: [PRODUCT_ID, "other"],
      }),
    ).toEqual({ assistant_ids: [PRODUCT_ID, "other"] });
    expect(
      toApiKeyChanges(scoped, { name: "portal-cliente", scope: "all", assistantIds: [] }),
    ).toEqual({ assistant_ids: null });
    expect(
      toApiKeyChanges(makeApiKey(), {
        name: "portal-cliente",
        scope: "selected",
        assistantIds: [PRODUCT_ID],
      }),
    ).toEqual({ assistant_ids: [PRODUCT_ID] });
  });
});
