import { describe, expect, it } from "vitest";

import { i18n } from "@/i18n";
import {
  makeCollection,
  makeProvider,
  makeProviders,
  OTHER_PROVIDER_ID,
  PROVIDER_ID,
} from "@/test/factories";

import {
  collectionChanges,
  collectionFormDefaults,
  collectionFormSchema,
  collectionInput,
  DEFAULT_EMBEDDING_MODEL,
  defaultEmbeddingModel,
  embeddingModelOptions,
  embeddingProviders,
  isEmbeddingLocked,
  isSuggestedModel,
  OPENROUTER_EMBEDDING_MODELS,
} from "./collectionForm";

const t = i18n.t.bind(i18n);

describe("collectionForm", () => {
  it.each([
    ["openai", "text-embedding-3-small"],
    ["openrouter", DEFAULT_EMBEDDING_MODEL],
    ["fake", DEFAULT_EMBEDDING_MODEL],
    [undefined, DEFAULT_EMBEDDING_MODEL],
  ] as const)("test_default_embedding_model_for_%s", (kind, model) => {
    expect(defaultEmbeddingModel(kind)).toBe(model);
  });

  it.each([
    ["openai", ["text-embedding-3-small"]],
    [
      "openrouter",
      [DEFAULT_EMBEDDING_MODEL, "google/gemini-embedding-001", "google/gemini-embedding-2"],
    ],
    [undefined, OPENROUTER_EMBEDDING_MODELS],
  ] as const)("test_embedding_model_options_for_%s", (kind, models) => {
    expect(embeddingModelOptions(kind)).toEqual(models);
  });

  it("test_is_suggested_model_only_for_blank_and_defaults", () => {
    expect(isSuggestedModel("")).toBe(true);
    expect(isSuggestedModel("text-embedding-3-small")).toBe(true);
    expect(isSuggestedModel(DEFAULT_EMBEDDING_MODEL)).toBe(true);
    expect(isSuggestedModel("custom-model")).toBe(false);
  });

  it("test_embedding_providers_leave_anthropic_out", () => {
    expect(embeddingProviders(makeProviders()).map((item) => item.id)).toEqual([PROVIDER_ID]);
  });

  it("test_is_embedding_locked_with_documents_only", () => {
    expect(isEmbeddingLocked(undefined)).toBe(false);
    expect(isEmbeddingLocked(makeCollection({ document_count: 0 }))).toBe(false);
    expect(isEmbeddingLocked(makeCollection())).toBe(true);
  });

  it("test_collection_form_defaults_pick_first_provider_and_its_model", () => {
    const openrouter = makeProvider({ id: OTHER_PROVIDER_ID, kind: "openrouter" });

    expect(collectionFormDefaults(undefined, [openrouter])).toEqual({
      name: "",
      description: "",
      providerId: OTHER_PROVIDER_ID,
      model: DEFAULT_EMBEDDING_MODEL,
    });
    expect(collectionFormDefaults(undefined, []).providerId).toBe("");
  });

  it("test_collection_form_round_trips_a_collection", () => {
    const collection = makeCollection();
    const values = collectionFormDefaults(collection, []);

    expect(collectionInput(values)).toEqual({
      name: collection.name,
      description: collection.description,
      provider_id: collection.provider_id,
      embedding_model: collection.embedding_model,
    });
  });

  it("test_collection_changes_skip_embedding_when_locked", () => {
    const values = collectionFormDefaults(makeCollection(), []);

    expect(collectionChanges(values, true)).toEqual({
      name: values.name,
      description: values.description,
    });
    expect(collectionChanges(values, false)).toEqual({
      name: values.name,
      description: values.description,
      provider_id: values.providerId,
      embedding_model: values.model,
    });
  });

  it("test_collection_form_schema_validates_fields", () => {
    const result = collectionFormSchema(t).safeParse({
      name: " ",
      description: "d".repeat(1001),
      providerId: "",
      model: "text embedding",
    });

    expect(result.error?.issues.map((issue) => issue.message)).toEqual([
      "Informe o nome da coleção.",
      "Use no máximo 1000 caracteres.",
      "Escolha uma credencial de embedding.",
      "O identificador do modelo não pode ter espaços.",
    ]);
  });
});
