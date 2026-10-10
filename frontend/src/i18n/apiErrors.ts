import type { TFunction } from "i18next";

import { ApiError } from "@/lib/api/client";

import ptBR from "./locales/pt-BR.json";

type ApiErrorKey = keyof (typeof ptBR)["apiErrors"];

function isKnownKey(code: string): code is ApiErrorKey {
  return Object.hasOwn(ptBR.apiErrors, code);
}

/**
 * Translation key for an error thrown by `lib/api`: the API `code` when the interface knows it,
 * `network` for a failed `fetch` and `unknown` for everything else.
 */
export function apiErrorKey(error: unknown): `apiErrors.${ApiErrorKey}` {
  if (error instanceof ApiError && error.code !== undefined && isKnownKey(error.code)) {
    return `apiErrors.${error.code}`;
  }
  if (error instanceof TypeError) {
    return "apiErrors.network";
  }
  return "apiErrors.unknown";
}

/** User-facing message (pt-BR via i18n) for an error thrown by `lib/api`. */
export function translateApiError(error: unknown, t: TFunction): string {
  return t(apiErrorKey(error));
}

/**
 * User-facing message for an error `code` reported inside a successful answer (e.g. the result
 * of a provider connection test); `unknown` when the interface does not know the code.
 */
export function translateApiErrorCode(code: string, t: TFunction): string {
  return t(isKnownKey(code) ? `apiErrors.${code}` : "apiErrors.unknown");
}
