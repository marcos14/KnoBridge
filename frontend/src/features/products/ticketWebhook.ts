import type { TFunction } from "i18next";

import { translateApiError, translateApiErrorCode } from "@/i18n/apiErrors";
import { ApiError } from "@/lib/api/client";

/** Longest `ticket_webhook_url` the API accepts (docs/specs/chamados.md, "Configuração"). */
export const WEBHOOK_URL_MAX_LENGTH = 2000;

/**
 * Whether `text` is a URL the panel lets through: `http` or `https`, without user and password.
 * The server applies the real rules on save (https only, except the hosts it allows in
 * development; no internal or reserved address) and answers with the reason.
 */
export function isWebhookUrl(text: string): boolean {
  let url: URL;
  try {
    url = new URL(text.trim());
  } catch {
    return false;
  }
  return (
    (url.protocol === "https:" || url.protocol === "http:") &&
    url.username === "" &&
    url.password === ""
  );
}

/**
 * `details.reason` of `webhook_url_invalid`, `webhook_destination_blocked` and
 * `webhook_unreachable`, as the spec lists them.
 */
export const WEBHOOK_REASONS = [
  "malformed",
  "scheme_not_https",
  "host_missing",
  "credentials_in_url",
  "host_unresolvable",
  "loopback",
  "private",
  "link_local",
  "cgnat",
  "unspecified",
  "multicast",
  "reserved",
  "timeout",
  "network",
] as const;

export type WebhookReason = (typeof WEBHOOK_REASONS)[number];

function field(details: unknown, name: string): unknown {
  return typeof details === "object" && details !== null && name in details
    ? (details as Record<string, unknown>)[name]
    : undefined;
}

/**
 * The message for a webhook error `code`, with what the details add: the reason (bad URL, blocked
 * destination, unreachable) or the HTTP status the destination answered.
 */
export function webhookErrorText(code: string, details: unknown, t: TFunction): string {
  const message = translateApiErrorCode(code, t);
  const reason = WEBHOOK_REASONS.find((item) => item === field(details, "reason"));
  if (reason !== undefined) {
    return t("products.webhook.withReason", {
      message,
      reason: t(`products.webhook.reasons.${reason}`),
    });
  }
  const status = field(details, "status");
  if (typeof status === "number") {
    return t("products.webhook.withStatus", { message, status });
  }
  return message;
}

/** Message of an error thrown by `lib/api`, with the webhook reason when the API gave one. */
export function webhookApiErrorText(error: unknown, t: TFunction): string {
  return error instanceof ApiError && error.code !== undefined
    ? webhookErrorText(error.code, error.details, t)
    : translateApiError(error, t);
}
