import type { TFunction } from "i18next";
import { z } from "zod";

import type { Provider, ProviderChanges, ProviderInput, ProviderKind } from "@/lib/api/providers";
import { NAME_MAX_LENGTH } from "@/lib/schemas";

/** Kinds offered by the form, in display order (`fake` is refused by the API in production). */
export const PROVIDER_KINDS: readonly ProviderKind[] = [
  "openai",
  "anthropic",
  "openrouter",
  "fake",
];

/** Limits of the contract (`api/providers.py`). */
export const BASE_URL_MAX_LENGTH = 500;
export const BASE_URL_PATTERN = /^https?:\/\/[^\s/]+(\/\S*)?$/;
export const API_KEY_MIN_LENGTH = 8;
export const API_KEY_MAX_LENGTH = 4096;

export interface ProviderFormValues {
  kind: ProviderKind;
  name: string;
  baseUrl: string;
  apiKey: string;
}

/**
 * Schema of the provider form. The key is required on create; on edit a blank key keeps the
 * stored one.
 */
export function providerFormSchema(t: TFunction, editing: boolean) {
  const tooLong = (max: number) => ({ error: t("auth.validation.tooLong", { max }) });
  const apiKey = z
    .string()
    .trim()
    .max(API_KEY_MAX_LENGTH, tooLong(API_KEY_MAX_LENGTH))
    .refine((value) => editing || value !== "", {
      error: t("providers.form.validation.apiKeyRequired"),
      abort: true,
    })
    .refine((value) => value === "" || value.length >= API_KEY_MIN_LENGTH, {
      error: t("providers.form.validation.apiKeyTooShort", { min: API_KEY_MIN_LENGTH }),
    });
  return z.object({
    kind: z.enum(PROVIDER_KINDS),
    name: z
      .string()
      .trim()
      .min(1, { error: t("providers.form.validation.nameRequired") })
      .max(NAME_MAX_LENGTH, tooLong(NAME_MAX_LENGTH)),
    baseUrl: z
      .string()
      .trim()
      .max(BASE_URL_MAX_LENGTH, tooLong(BASE_URL_MAX_LENGTH))
      .refine((value) => value === "" || BASE_URL_PATTERN.test(value), {
        error: t("providers.form.validation.baseUrlInvalid"),
      }),
    apiKey,
  });
}

/** Initial values: blank for a new provider; the stored data (never the key) for an edit. */
export function providerFormDefaults(provider?: Provider): ProviderFormValues {
  return {
    kind: provider?.kind ?? "openai",
    name: provider?.name ?? "",
    baseUrl: provider?.base_url ?? "",
    apiKey: "",
  };
}

/** Body of `POST .../providers`; a blank `base_url` is left out (the provider's default). */
export function createBody({ kind, name, baseUrl, apiKey }: ProviderFormValues): ProviderInput {
  return { kind, name, api_key: apiKey, ...(baseUrl === "" ? {} : { base_url: baseUrl }) };
}

/** Body of `PATCH .../providers/{id}`: blank `base_url` clears it; a blank key keeps the stored one. */
export function updateBody({ name, baseUrl, apiKey }: ProviderFormValues): ProviderChanges {
  return {
    name,
    base_url: baseUrl === "" ? null : baseUrl,
    ...(apiKey === "" ? {} : { api_key: apiKey }),
  };
}
