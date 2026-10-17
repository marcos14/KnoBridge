import { describe, expect, it } from "vitest";

import { i18n } from "@/i18n";
import { COLLECTION_ID, makeProduct, OTHER_COLLECTION_ID } from "@/test/factories";

import {
  productBody,
  productFormDefaults,
  productFormSchema,
  parseMinSimilarity,
} from "./productForm";

const t = i18n.t.bind(i18n);

describe("parseMinSimilarity", () => {
  it.each([
    ["0", 0],
    ["0,3", 0.3],
    [" 1 ", 1],
  ])("test_parse_min_similarity_accepts_%s", (text, value) => {
    expect(parseMinSimilarity(text)).toBe(value);
  });

  it.each(["", "abc", "-0.1", "1.1", ".5", "1e1", "1."])(
    "test_parse_min_similarity_rejects_%s",
    (text) => {
      expect(parseMinSimilarity(text)).toBeNull();
    },
  );
});

describe("productForm", () => {
  it("test_product_form_defaults_follow_the_contract", () => {
    expect(productFormDefaults(undefined)).toEqual({
      name: "",
      description: "",
      instructions: "",
      language: "pt-BR",
      tone: "neutral",
      noSourceMessage: "",
      active: true,
      collectionIds: [],
      minSimilarity: "",
      rerank: true,
      ticketWebhookEnabled: false,
      ticketWebhookUrl: "",
    });
  });

  it("test_product_form_round_trips_a_product", () => {
    const product = makeProduct({
      active: false,
      collection_ids: [COLLECTION_ID, OTHER_COLLECTION_ID],
      min_similarity: 0.55,
    });

    expect(productBody(productFormDefaults(product))).toEqual({
      name: product.name,
      description: product.description,
      instructions: product.instructions,
      language: product.language,
      tone: product.tone,
      no_source_message: product.no_source_message,
      active: false,
      collection_ids: [COLLECTION_ID, OTHER_COLLECTION_ID],
      min_similarity: 0.55,
      rerank: true,
      ticket_webhook_url: null,
    });
  });

  it("test_product_body_keeps_the_saved_rerank_option", () => {
    const product = makeProduct({ rerank: false });

    expect(productBody(productFormDefaults(product), product).rerank).toBe(false);
    expect(productBody({ ...productFormDefaults(product), rerank: true }, product).rerank).toBe(
      true,
    );
  });

  it("test_product_form_reads_a_null_min_similarity_as_blank_and_sends_null", () => {
    const product = makeProduct({ min_similarity: null });

    const values = productFormDefaults(product);

    expect(values.minSimilarity).toBe("");
    expect(productBody(values, product).min_similarity).toBeNull();
  });

  it("test_product_form_reads_the_webhook_of_a_product", () => {
    const product = makeProduct({ ticket_webhook_url: "https://chamados.example.test/kb" });

    const values = productFormDefaults(product);

    expect([values.ticketWebhookEnabled, values.ticketWebhookUrl]).toEqual([
      true,
      "https://chamados.example.test/kb",
    ]);
  });

  it("test_product_body_leaves_an_unchanged_webhook_out_of_the_patch", () => {
    const product = makeProduct({ ticket_webhook_url: "https://chamados.example.test/kb" });
    const values = productFormDefaults(product);

    expect(productBody(values, product)).not.toHaveProperty("ticket_webhook_url");
    expect(
      productBody({ ...values, ticketWebhookUrl: "https://novo.example.test/kb" }, product),
    ).toHaveProperty("ticket_webhook_url", "https://novo.example.test/kb");
    expect(productBody({ ...values, ticketWebhookEnabled: false }, product)).toHaveProperty(
      "ticket_webhook_url",
      null,
    );
  });

  it.each([
    ["", "Informe a URL do webhook."],
    ["chamados.example.test", "Informe uma URL http ou https válida, sem usuário e senha."],
  ])("test_product_form_schema_checks_the_webhook_url_%s", (url, message) => {
    const values = {
      ...productFormDefaults(undefined),
      name: "Ok",
      ticketWebhookEnabled: true,
      ticketWebhookUrl: url,
    };

    const result = productFormSchema(t).safeParse(values);

    expect(result.error?.issues.map((issue) => [issue.path, issue.message])).toEqual([
      [["ticketWebhookUrl"], message],
    ]);
  });

  it("test_product_form_schema_ignores_the_url_with_the_webhook_off", () => {
    const values = {
      ...productFormDefaults(undefined),
      name: "Ok",
      ticketWebhookUrl: "não é url",
    };

    expect(productFormSchema(t).safeParse(values).success).toBe(true);
  });

  it("test_product_form_schema_accepts_a_webhook_url", () => {
    const values = {
      ...productFormDefaults(undefined),
      name: "Ok",
      ticketWebhookEnabled: true,
      ticketWebhookUrl: " https://chamados.example.test/kb ",
    };

    const result = productFormSchema(t).safeParse(values);

    expect(result.data?.ticketWebhookUrl).toBe("https://chamados.example.test/kb");
  });

  it("test_product_body_reads_min_similarity_with_comma_or_blank_as_the_default", () => {
    const values = productFormDefaults(undefined);

    expect(productBody({ ...values, minSimilarity: "0,45" }).min_similarity).toBe(0.45);
    expect(productBody({ ...values, minSimilarity: " " }).min_similarity).toBeNull();
  });

  it("test_product_form_schema_accepts_a_blank_min_similarity", () => {
    const values = { ...productFormDefaults(undefined), name: "Ok", minSimilarity: " " };

    expect(productFormSchema(t).safeParse(values).success).toBe(true);
  });

  it("test_product_form_schema_rejects_min_similarity_out_of_range", () => {
    const values = { ...productFormDefaults(undefined), name: "Ok", minSimilarity: "1.5" };

    const result = productFormSchema(t).safeParse(values);

    expect(result.error?.issues.map((issue) => issue.message)).toEqual([
      "Informe um número de 0 a 1.",
    ]);
  });

  it("test_product_form_schema_limits_lengths", () => {
    const values = {
      ...productFormDefaults(undefined),
      name: "Ok",
      description: "d".repeat(1001),
      instructions: "s".repeat(20001),
      noSourceMessage: "n".repeat(2001),
    };

    const result = productFormSchema(t).safeParse(values);

    expect(result.error?.issues.map((issue) => issue.message)).toEqual([
      "Use no máximo 1000 caracteres.",
      "Use no máximo 20000 caracteres.",
      "Use no máximo 2000 caracteres.",
    ]);
  });

  it("test_product_form_schema_requires_a_name", () => {
    const result = productFormSchema(t).safeParse(productFormDefaults(undefined));

    expect(result.error?.issues.map((issue) => issue.path)).toEqual([["name"]]);
  });
});
