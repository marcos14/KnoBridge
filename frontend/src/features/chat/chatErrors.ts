import type { TFunction } from "i18next";

import { translateApiError } from "@/i18n/apiErrors";
import { ApiError } from "@/lib/api/client";
import type { ResponseLevel } from "@/lib/api/levels";
import { levelLabel, parseLevel } from "@/lib/responseLevels";

function detail(error: ApiError, key: string): ResponseLevel | undefined {
  const { details } = error;
  if (typeof details !== "object" || details === null) {
    return undefined;
  }
  const value: unknown = (details as Record<string, unknown>)[key];
  return typeof value === "string" ? parseLevel(value) : undefined;
}

/**
 * What the chat says when starting a conversation or sending a question fails. The level errors
 * of `docs/specs/produtos-e-niveis.md` ("Chat com produto e nível") name the levels from their
 * `details`: a level above the member's maximum, a level without a model ("ask an admin") and an
 * inactive product. Anything else is the usual message of the error code.
 */
export function chatErrorMessage(error: unknown, t: TFunction): string {
  if (error instanceof ApiError) {
    if (error.code === "level_not_allowed") {
      const requested = detail(error, "requested_level");
      const max = detail(error, "max_level");
      if (requested !== undefined && max !== undefined) {
        return t("chat.errors.levelNotAllowed", {
          requested: levelLabel(requested, t),
          max: levelLabel(max, t),
        });
      }
    }
    if (error.code === "level_not_configured") {
      const level = detail(error, "level");
      return level === undefined
        ? t("chat.errors.levelNotConfiguredUnknown")
        : t("chat.errors.levelNotConfigured", { level: levelLabel(level, t) });
    }
    if (error.code === "product_inactive") {
      return t("chat.errors.productInactive");
    }
  }
  return translateApiError(error, t);
}
