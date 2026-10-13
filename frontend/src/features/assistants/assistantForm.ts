import type { TFunction } from "i18next";
import { z } from "zod";

import type { Assistant, AssistantInput, AssistantTone } from "@/lib/api/assistants";
import { NAME_MAX_LENGTH } from "@/lib/schemas";

import { isWebhookUrl, WEBHOOK_URL_MAX_LENGTH } from "./ticketWebhook";

/** Tones offered by the form, in display order. */
export const ASSISTANT_TONES: readonly AssistantTone[] = ["neutral", "formal", "friendly"];

/**
 * Limits and defaults of the contract (`api/products.py`, `products/models.py`). Since plan 0009
 * the provider, model and temperature belong to the levels of the workspace, not to the product.
 */
export const DESCRIPTION_MAX_LENGTH = 1000;
export const SYSTEM_PROMPT_MAX_LENGTH = 20000;
export const LANGUAGE_MAX_LENGTH = 35;
export const NO_SOURCE_MESSAGE_MAX_LENGTH = 2000;
export const LANGUAGE_PATTERN = /^[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})*$/;
export const DEFAULT_LANGUAGE = "pt-BR";
export const MAX_MIN_SIMILARITY = 1;
export const DEFAULT_MIN_SIMILARITY = 0.35;

/**
 * Minimum similarity typed as text, with a comma or a dot as decimal separator ("0,45", "0.3");
 * `null` when it is not a plain number from 0 to 1.
 */
export function parseMinSimilarity(text: string): number | null {
  const normalized = text.trim().replace(",", ".");
  if (!/^\d+(\.\d+)?$/.test(normalized)) {
    return null;
  }
  const value = Number(normalized);
  return value <= MAX_MIN_SIMILARITY ? value : null;
}

export interface AssistantFormValues {
  name: string;
  description: string;
  /** The extra instructions of the product (`instructions` in the API). */
  systemPrompt: string;
  language: string;
  tone: AssistantTone;
  noSourceMessage: string;
  active: boolean;
  collectionIds: string[];
  minSimilarity: string;
  /** Whether the chat offers "Abrir chamado" (off sends `ticket_webhook_url: null`). */
  ticketWebhookEnabled: boolean;
  ticketWebhookUrl: string;
}

export function assistantFormSchema(t: TFunction) {
  const tooLong = (max: number) => ({ error: t("auth.validation.tooLong", { max }) });
  const text = (max: number) => z.string().trim().max(max, tooLong(max));
  return z
    .object({
      name: text(NAME_MAX_LENGTH).min(1, { error: t("assistants.form.validation.nameRequired") }),
      description: text(DESCRIPTION_MAX_LENGTH),
      systemPrompt: text(SYSTEM_PROMPT_MAX_LENGTH),
      language: text(LANGUAGE_MAX_LENGTH).regex(LANGUAGE_PATTERN, {
        error: t("assistants.form.validation.languageInvalid"),
      }),
      tone: z.enum(ASSISTANT_TONES),
      noSourceMessage: text(NO_SOURCE_MESSAGE_MAX_LENGTH),
      active: z.boolean(),
      collectionIds: z.array(z.string()),
      minSimilarity: z.string().refine((value) => parseMinSimilarity(value) !== null, {
        error: t("assistants.form.validation.minSimilarityInvalid"),
      }),
      ticketWebhookEnabled: z.boolean(),
      ticketWebhookUrl: text(WEBHOOK_URL_MAX_LENGTH),
    })
    .superRefine((values, ctx) => {
      // Off, the URL is not sent (it is cleared), so whatever is typed does not matter.
      if (!values.ticketWebhookEnabled) {
        return;
      }
      const message =
        values.ticketWebhookUrl === ""
          ? t("assistants.webhook.validation.urlRequired")
          : isWebhookUrl(values.ticketWebhookUrl)
            ? null
            : t("assistants.webhook.validation.urlInvalid");
      if (message !== null) {
        ctx.addIssue({ code: "custom", path: ["ticketWebhookUrl"], message });
      }
    });
}

/** Initial values: the stored assistant for an edit; otherwise the contract's defaults. */
export function assistantFormDefaults(assistant: Assistant | undefined): AssistantFormValues {
  if (assistant === undefined) {
    return {
      name: "",
      description: "",
      systemPrompt: "",
      language: DEFAULT_LANGUAGE,
      tone: "neutral",
      noSourceMessage: "",
      active: true,
      collectionIds: [],
      minSimilarity: String(DEFAULT_MIN_SIMILARITY),
      ticketWebhookEnabled: false,
      ticketWebhookUrl: "",
    };
  }
  return {
    name: assistant.name,
    description: assistant.description,
    systemPrompt: assistant.instructions,
    language: assistant.language,
    tone: assistant.tone,
    noSourceMessage: assistant.no_source_message,
    active: assistant.active,
    collectionIds: [...assistant.collection_ids],
    minSimilarity: String(assistant.min_similarity),
    ticketWebhookEnabled: assistant.ticket_webhook_url !== null,
    ticketWebhookUrl: assistant.ticket_webhook_url ?? "",
  };
}

/**
 * Body of both `POST` and `PATCH` (every field is sent): a blank `no_source_message` makes the
 * backend store its default message; `collection_ids` replaces the whole set. The webhook URL
 * (`null` when off) is left out when it is the one `current` already has: the server checks the
 * destination again whenever it receives one, and an unchanged URL needs no new check.
 */
export function assistantBody(values: AssistantFormValues, current?: Assistant): AssistantInput {
  const webhookUrl = values.ticketWebhookEnabled ? values.ticketWebhookUrl : null;
  const webhook =
    current?.ticket_webhook_url === webhookUrl ? {} : { ticket_webhook_url: webhookUrl };
  return {
    ...webhook,
    name: values.name,
    description: values.description,
    instructions: values.systemPrompt,
    language: values.language,
    tone: values.tone,
    no_source_message: values.noSourceMessage,
    active: values.active,
    // The whole set is sent: on a PATCH it replaces the assistant's collections.
    collection_ids: values.collectionIds,
    min_similarity: parseMinSimilarity(values.minSimilarity) ?? DEFAULT_MIN_SIMILARITY,
  };
}
