import type { TFunction } from "i18next";
import { z } from "zod";

import type { ApiKey, ApiKeyChanges, ApiKeyInput } from "@/lib/api/apiKeys";
import { RESPONSE_LEVELS, type ResponseLevel } from "@/lib/api/levels";
import { NAME_MAX_LENGTH } from "@/lib/schemas";

/** Most products a key's scope may list (`ApiKeyCreate.product_ids`). */
export const API_KEY_SCOPE_MAX = 100;

/**
 * Maximum level a new key starts with in the form. The API has no default (`max_level` is
 * required, so whoever creates the key chooses on purpose); the panel pre-selects the lowest
 * level, `end_user` (`docs/specs/api-publica.md`, "Chaves: escopo e nível máximo").
 */
export const API_KEY_DEFAULT_MAX_LEVEL: ResponseLevel = "end_user";

export type ApiKeyScope = "all" | "selected";

export interface ApiKeyFormValues {
  name: string;
  /** `all`: every active product, also the ones created later (`product_ids: null`). */
  scope: ApiKeyScope;
  productIds: string[];
  /** The highest level the key asks in, in any product of its scope. */
  maxLevel: ResponseLevel;
}

export function apiKeyFormSchema(t: TFunction) {
  return z
    .object({
      name: z
        .string()
        .trim()
        .min(1, { error: t("apiKeys.form.validation.nameRequired") })
        .max(NAME_MAX_LENGTH, { error: t("auth.validation.tooLong", { max: NAME_MAX_LENGTH }) }),
      scope: z.enum(["all", "selected"]),
      productIds: z.array(z.string()),
      maxLevel: z.enum(RESPONSE_LEVELS),
    })
    .superRefine((values, context) => {
      if (values.scope === "all") {
        return;
      }
      if (values.productIds.length === 0) {
        context.addIssue({
          code: "custom",
          path: ["productIds"],
          message: t("apiKeys.form.validation.productsRequired"),
        });
      } else if (values.productIds.length > API_KEY_SCOPE_MAX) {
        context.addIssue({
          code: "custom",
          path: ["productIds"],
          message: t("apiKeys.form.validation.tooManyProducts", { max: API_KEY_SCOPE_MAX }),
        });
      }
    });
}

/** Form values of an existing key, or of a new one (every product, the lowest level). */
export function apiKeyFormDefaults(apiKey?: ApiKey): ApiKeyFormValues {
  if (apiKey === undefined) {
    return { name: "", scope: "all", productIds: [], maxLevel: API_KEY_DEFAULT_MAX_LEVEL };
  }
  return {
    name: apiKey.name,
    scope: apiKey.product_ids === null ? "all" : "selected",
    productIds: apiKey.product_ids ?? [],
    maxLevel: apiKey.max_level,
  };
}

function scopeOf(values: ApiKeyFormValues): string[] | null {
  return values.scope === "all" ? null : values.productIds;
}

/** Body of `POST .../api-keys`. */
export function toApiKeyInput(values: ApiKeyFormValues): ApiKeyInput {
  return {
    name: values.name.trim(),
    product_ids: scopeOf(values),
    max_level: values.maxLevel,
  };
}

function sameScope(current: string[] | null, next: string[] | null): boolean {
  if (current === null || next === null) {
    return current === next;
  }
  const remaining = new Set(current);
  return current.length === next.length && next.every((id) => remaining.has(id));
}

/** Body of `PATCH .../api-keys/{id}` with only what changed; `null` when nothing did. */
export function toApiKeyChanges(apiKey: ApiKey, values: ApiKeyFormValues): ApiKeyChanges | null {
  const changes: ApiKeyChanges = {};
  const name = values.name.trim();
  if (name !== apiKey.name) {
    changes.name = name;
  }
  const scope = scopeOf(values);
  if (!sameScope(apiKey.product_ids, scope)) {
    changes.product_ids = scope;
  }
  if (values.maxLevel !== apiKey.max_level) {
    changes.max_level = values.maxLevel;
  }
  return Object.keys(changes).length === 0 ? null : changes;
}
