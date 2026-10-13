import type { TFunction } from "i18next";
import { describe, expect, it } from "vitest";

import { makeApiKey } from "@/test/apiKeyFactories";
import { PRODUCT_ID, OTHER_PRODUCT_ID } from "@/test/factories";

import {
  API_KEY_SCOPE_MAX,
  type ApiKeyFormValues,
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

function values(overrides: Partial<ApiKeyFormValues> = {}): ApiKeyFormValues {
  return {
    name: "portal-cliente",
    scope: "all",
    productIds: [],
    maxLevel: "product_dev",
    ...overrides,
  };
}

describe("apiKeyFormSchema", () => {
  it("test_api_key_form_schema_requires_a_name", () => {
    expect(issuesOf(values({ name: "  " }))).toEqual(["apiKeys.form.validation.nameRequired"]);
  });

  it("test_api_key_form_schema_ignores_products_when_scope_is_all", () => {
    expect(issuesOf(values())).toEqual([]);
  });

  it("test_api_key_form_schema_requires_one_to_max_products_when_selected", () => {
    expect(issuesOf(values({ scope: "selected" }))).toEqual([
      "apiKeys.form.validation.productsRequired",
    ]);
    const tooMany = Array.from({ length: API_KEY_SCOPE_MAX + 1 }, (_, index) => String(index));
    expect(issuesOf(values({ scope: "selected", productIds: tooMany }))).toEqual([
      "apiKeys.form.validation.tooManyProducts",
    ]);
    expect(issuesOf(values({ scope: "selected", productIds: [PRODUCT_ID] }))).toEqual([]);
  });

  it("test_api_key_form_schema_requires_a_known_level", () => {
    expect(issuesOf({ ...values(), maxLevel: "admin" })).toHaveLength(1);
  });
});

describe("apiKeyFormDefaults", () => {
  it("test_api_key_form_defaults_of_a_new_key_cover_every_product_at_end_user", () => {
    expect(apiKeyFormDefaults()).toEqual({
      name: "",
      scope: "all",
      productIds: [],
      maxLevel: "end_user",
    });
  });

  it("test_api_key_form_defaults_read_the_scope_and_level_of_an_existing_key", () => {
    expect(apiKeyFormDefaults(makeApiKey())).toMatchObject({ scope: "all", productIds: [] });
    expect(
      apiKeyFormDefaults(makeApiKey({ product_ids: [PRODUCT_ID], max_level: "support" })),
    ).toEqual(values({ scope: "selected", productIds: [PRODUCT_ID], maxLevel: "support" }));
  });
});

describe("toApiKeyInput", () => {
  it("test_to_api_key_input_trims_the_name_and_maps_the_scope_and_level", () => {
    expect(
      toApiKeyInput(values({ name: " portal ", productIds: [PRODUCT_ID], maxLevel: "end_user" })),
    ).toEqual({ name: "portal", product_ids: null, max_level: "end_user" });
    expect(
      toApiKeyInput(values({ name: "portal", scope: "selected", productIds: [PRODUCT_ID] })),
    ).toEqual({ name: "portal", product_ids: [PRODUCT_ID], max_level: "product_dev" });
  });
});

describe("toApiKeyChanges", () => {
  const scoped = makeApiKey({ product_ids: [PRODUCT_ID, OTHER_PRODUCT_ID] });

  it("test_to_api_key_changes_is_null_when_nothing_changed", () => {
    expect(
      toApiKeyChanges(
        scoped,
        values({
          name: " portal-cliente ",
          scope: "selected",
          productIds: [OTHER_PRODUCT_ID, PRODUCT_ID],
        }),
      ),
    ).toBeNull();
    expect(toApiKeyChanges(makeApiKey(), values())).toBeNull();
  });

  it("test_to_api_key_changes_sends_only_what_changed", () => {
    const selected = { scope: "selected" as const, productIds: [PRODUCT_ID, OTHER_PRODUCT_ID] };
    expect(toApiKeyChanges(scoped, values({ ...selected, name: "portal" }))).toEqual({
      name: "portal",
    });
    expect(
      toApiKeyChanges(scoped, values({ scope: "selected", productIds: [PRODUCT_ID] })),
    ).toEqual({ product_ids: [PRODUCT_ID] });
    expect(
      toApiKeyChanges(scoped, values({ scope: "selected", productIds: [PRODUCT_ID, "other"] })),
    ).toEqual({ product_ids: [PRODUCT_ID, "other"] });
    expect(toApiKeyChanges(scoped, values())).toEqual({ product_ids: null });
    expect(
      toApiKeyChanges(makeApiKey(), values({ scope: "selected", productIds: [PRODUCT_ID] })),
    ).toEqual({ product_ids: [PRODUCT_ID] });
    expect(toApiKeyChanges(makeApiKey(), values({ maxLevel: "support" }))).toEqual({
      max_level: "support",
    });
  });
});
