import type { TFunction } from "i18next";
import { z } from "zod";

import type { Assistant, AssistantInput, AssistantTone } from "@/lib/api/assistants";
import { NAME_MAX_LENGTH } from "@/lib/schemas";

/** Tones offered by the form, in display order. */
export const ASSISTANT_TONES: readonly AssistantTone[] = ["neutral", "formal", "friendly"];

/** Limits and defaults of the contract (`api/assistants.py`, `assistants/models.py`). */
export const DESCRIPTION_MAX_LENGTH = 1000;
export const SYSTEM_PROMPT_MAX_LENGTH = 20000;
export const MODEL_MAX_LENGTH = 200;
export const LANGUAGE_MAX_LENGTH = 35;
export const NO_SOURCE_MESSAGE_MAX_LENGTH = 2000;
export const LANGUAGE_PATTERN = /^[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})*$/;
export const MIN_TEMPERATURE = 0;
export const MAX_TEMPERATURE = 2;
export const DEFAULT_TEMPERATURE = 0.2;
export const DEFAULT_LANGUAGE = "pt-BR";
export const MAX_MIN_SIMILARITY = 1;
export const DEFAULT_MIN_SIMILARITY = 0.3;

/**
 * Temperature typed as text, with a comma or a dot as decimal separator ("0,7", "1.5"); `null`
 * when it is not a plain number from 0 to 2.
 */
export function parseTemperature(text: string): number | null {
  return parseBoundedDecimal(text, MAX_TEMPERATURE);
}

/**
 * Minimum similarity typed as text ("0,45", "0.3"); `null` when it is not a plain number from 0
 * to 1.
 */
export function parseMinSimilarity(text: string): number | null {
  return parseBoundedDecimal(text, MAX_MIN_SIMILARITY);
}

/** A plain non-negative decimal up to `max`, with a comma or a dot; `null` otherwise. */
function parseBoundedDecimal(text: string, max: number): number | null {
  const normalized = text.trim().replace(",", ".");
  if (!/^\d+(\.\d+)?$/.test(normalized)) {
    return null;
  }
  const value = Number(normalized);
  return value <= max ? value : null;
}

export interface AssistantFormValues {
  name: string;
  description: string;
  systemPrompt: string;
  providerId: string;
  model: string;
  temperature: string;
  language: string;
  tone: AssistantTone;
  noSourceMessage: string;
  active: boolean;
  collectionIds: string[];
  minSimilarity: string;
}

export function assistantFormSchema(t: TFunction) {
  const tooLong = (max: number) => ({ error: t("auth.validation.tooLong", { max }) });
  const text = (max: number) => z.string().trim().max(max, tooLong(max));
  return z.object({
    name: text(NAME_MAX_LENGTH).min(1, { error: t("assistants.form.validation.nameRequired") }),
    description: text(DESCRIPTION_MAX_LENGTH),
    systemPrompt: text(SYSTEM_PROMPT_MAX_LENGTH),
    providerId: z.string().min(1, { error: t("assistants.form.validation.providerRequired") }),
    model: text(MODEL_MAX_LENGTH)
      .min(1, { error: t("assistants.form.validation.modelRequired") })
      .regex(/^\S+$/, { error: t("assistants.form.validation.modelInvalid") }),
    temperature: z.string().refine((value) => parseTemperature(value) !== null, {
      error: t("assistants.form.validation.temperatureInvalid"),
    }),
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
  });
}

/**
 * Initial values: the stored assistant for an edit; otherwise the contract's defaults, on
 * `providerId` (the first provider, if any).
 */
export function assistantFormDefaults(
  assistant: Assistant | undefined,
  providerId: string,
): AssistantFormValues {
  if (assistant === undefined) {
    return {
      name: "",
      description: "",
      systemPrompt: "",
      providerId,
      model: "",
      temperature: String(DEFAULT_TEMPERATURE),
      language: DEFAULT_LANGUAGE,
      tone: "neutral",
      noSourceMessage: "",
      active: true,
      collectionIds: [],
      minSimilarity: String(DEFAULT_MIN_SIMILARITY),
    };
  }
  return {
    name: assistant.name,
    description: assistant.description,
    systemPrompt: assistant.system_prompt,
    providerId: assistant.provider_id,
    model: assistant.model,
    temperature: String(assistant.temperature),
    language: assistant.language,
    tone: assistant.tone,
    noSourceMessage: assistant.no_source_message,
    active: assistant.active,
    collectionIds: [...assistant.collection_ids],
    minSimilarity: String(assistant.min_similarity),
  };
}

/**
 * Body of both `POST` and `PATCH` (every field is sent): a blank `no_source_message` makes the
 * backend store its default message; `collection_ids` replaces the whole set.
 */
export function assistantBody(values: AssistantFormValues): AssistantInput {
  return {
    name: values.name,
    description: values.description,
    system_prompt: values.systemPrompt,
    provider_id: values.providerId,
    model: values.model,
    // The schema already accepted it, so it parses.
    temperature: parseTemperature(values.temperature) ?? DEFAULT_TEMPERATURE,
    language: values.language,
    tone: values.tone,
    no_source_message: values.noSourceMessage,
    active: values.active,
    // The whole set is sent: on a PATCH it replaces the assistant's collections.
    collection_ids: values.collectionIds,
    min_similarity: parseMinSimilarity(values.minSimilarity) ?? DEFAULT_MIN_SIMILARITY,
  };
}
