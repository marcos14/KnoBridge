import type { TFunction } from "i18next";
import { z } from "zod";

import type { ApiKey, ApiKeyChanges, ApiKeyInput } from "@/lib/api/apiKeys";
import { NAME_MAX_LENGTH } from "@/lib/schemas";

/** Most assistants a key's scope may list (`ApiKeyCreate.product_ids`). */
export const API_KEY_SCOPE_MAX = 100;

export type ApiKeyScope = "all" | "selected";

export interface ApiKeyFormValues {
  name: string;
  /** `all`: every active assistant, also the ones created later (`product_ids: null`). */
  scope: ApiKeyScope;
  assistantIds: string[];
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
      assistantIds: z.array(z.string()),
    })
    .superRefine((values, context) => {
      if (values.scope === "all") {
        return;
      }
      if (values.assistantIds.length === 0) {
        context.addIssue({
          code: "custom",
          path: ["assistantIds"],
          message: t("apiKeys.form.validation.assistantsRequired"),
        });
      } else if (values.assistantIds.length > API_KEY_SCOPE_MAX) {
        context.addIssue({
          code: "custom",
          path: ["assistantIds"],
          message: t("apiKeys.form.validation.tooManyAssistants", { max: API_KEY_SCOPE_MAX }),
        });
      }
    });
}

/** Form values of an existing key, or of a new one (every assistant). */
export function apiKeyFormDefaults(apiKey?: ApiKey): ApiKeyFormValues {
  if (apiKey === undefined) {
    return { name: "", scope: "all", assistantIds: [] };
  }
  return {
    name: apiKey.name,
    scope: apiKey.product_ids === null ? "all" : "selected",
    assistantIds: apiKey.product_ids ?? [],
  };
}

function scopeOf(values: ApiKeyFormValues): string[] | null {
  return values.scope === "all" ? null : values.assistantIds;
}

/**
 * Maximum level of a key created here (`ApiKeyCreate.max_level`, required by the API). Until the
 * form lets the admin choose it (plan 0009, F3.3), new keys keep the reach keys always had: every
 * source, as the migrated keys.
 */
export const API_KEY_DEFAULT_MAX_LEVEL = "product_dev" satisfies ApiKeyInput["max_level"];

/** Body of `POST .../api-keys`. */
export function toApiKeyInput(values: ApiKeyFormValues): ApiKeyInput {
  return {
    name: values.name.trim(),
    product_ids: scopeOf(values),
    max_level: API_KEY_DEFAULT_MAX_LEVEL,
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
  return Object.keys(changes).length === 0 ? null : changes;
}
