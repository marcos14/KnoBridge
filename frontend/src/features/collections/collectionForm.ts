import type { TFunction } from "i18next";
import { z } from "zod";

import type { Collection, CollectionChanges, CollectionInput } from "@/lib/api/collections";
import type { Provider, ProviderKind } from "@/lib/api/providers";
import { NAME_MAX_LENGTH } from "@/lib/schemas";

/** Limits of the contract (`api/collections.py`). */
export const DESCRIPTION_MAX_LENGTH = 1000;
export const MODEL_MAX_LENGTH = 200;

/**
 * The embedding model of the index (decision D2 of plan 0003: 1536 dimensions). OpenRouter names
 * it with the vendor prefix; the OpenAI API itself, without it.
 */
export const DEFAULT_EMBEDDING_MODEL = "openai/text-embedding-3-small";
const OPENAI_EMBEDDING_MODEL = "text-embedding-3-small";

/** Model suggested for a credential of `kind`; the fake provider accepts any text. */
export function defaultEmbeddingModel(kind: ProviderKind | undefined): string {
  return kind === "openai" ? OPENAI_EMBEDDING_MODEL : DEFAULT_EMBEDDING_MODEL;
}

/**
 * Models known to give 1536-dimension vectors through OpenRouter. The Gemini ones default to 3072;
 * the backend asks for 1536 explicitly.
 */
export const OPENROUTER_EMBEDDING_MODELS: readonly string[] = [
  DEFAULT_EMBEDDING_MODEL,
  "google/gemini-embedding-001",
  "google/gemini-embedding-2",
];

/** Models offered in the field for a credential of `kind`; any other id may still be typed. */
export function embeddingModelOptions(kind: ProviderKind | undefined): readonly string[] {
  return kind === "openai" ? [OPENAI_EMBEDDING_MODEL] : OPENROUTER_EMBEDDING_MODELS;
}

/** Whether `model` is one of the suggestions, so switching provider may replace it. */
export function isSuggestedModel(model: string): boolean {
  return model === "" || model === DEFAULT_EMBEDDING_MODEL || model === OPENAI_EMBEDDING_MODEL;
}

/** Credentials that can embed: every kind but Anthropic, which has no embeddings API. */
export function embeddingProviders(providers: readonly Provider[]): Provider[] {
  return providers.filter((provider) => provider.kind !== "anthropic");
}

/** Provider and model cannot change once the collection has documents (409 otherwise). */
export function isEmbeddingLocked(collection: Collection | undefined): boolean {
  return collection !== undefined && collection.document_count > 0;
}

export interface CollectionFormValues {
  name: string;
  description: string;
  providerId: string;
  model: string;
}

export function collectionFormSchema(t: TFunction) {
  const tooLong = (max: number) => ({ error: t("auth.validation.tooLong", { max }) });
  const text = (max: number) => z.string().trim().max(max, tooLong(max));
  return z.object({
    name: text(NAME_MAX_LENGTH).min(1, { error: t("collections.form.validation.nameRequired") }),
    description: text(DESCRIPTION_MAX_LENGTH),
    providerId: z.string().min(1, { error: t("collections.form.validation.providerRequired") }),
    model: text(MODEL_MAX_LENGTH)
      .min(1, { error: t("collections.form.validation.modelRequired") })
      .regex(/^\S+$/, { error: t("collections.form.validation.modelInvalid") }),
  });
}

/**
 * Initial values: the stored collection for an edit; otherwise the first embedding credential and
 * the model suggested for it.
 */
export function collectionFormDefaults(
  collection: Collection | undefined,
  providers: readonly Provider[],
): CollectionFormValues {
  if (collection !== undefined) {
    return {
      name: collection.name,
      description: collection.description,
      providerId: collection.provider_id,
      model: collection.embedding_model,
    };
  }
  const first = providers[0];
  return {
    name: "",
    description: "",
    providerId: first?.id ?? "",
    model: defaultEmbeddingModel(first?.kind),
  };
}

/** Body of `POST`. */
export function collectionInput(values: CollectionFormValues): CollectionInput {
  return {
    name: values.name,
    description: values.description,
    provider_id: values.providerId,
    embedding_model: values.model,
  };
}

/** Body of `PATCH`: provider and model only while they may still change. */
export function collectionChanges(
  values: CollectionFormValues,
  embeddingLocked: boolean,
): CollectionChanges {
  const changes: CollectionChanges = { name: values.name, description: values.description };
  if (!embeddingLocked) {
    changes.provider_id = values.providerId;
    changes.embedding_model = values.model;
  }
  return changes;
}
