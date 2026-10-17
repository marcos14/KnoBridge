import { describe, expect, it } from "vitest";

import { i18n } from "@/i18n";
import { makeCommitSearchResult, makeSearchResult } from "@/test/factories";

import {
  formatScore,
  parseMinSimilarity,
  resultLanguage,
  resultLocation,
  searchBody,
  searchFormSchema,
} from "./searchResult";

const t = i18n.t.bind(i18n);

describe("searchResult", () => {
  it.each([
    ["0", 0],
    ["0.45", 0.45],
    [" 0,5 ", 0.5],
    ["1", 1],
  ])("test_parse_min_similarity_accepts_%s", (text, value) => {
    expect(parseMinSimilarity(text)).toBe(value);
  });

  it.each(["", "abc", "-0.1", "1.1", ".5"])("test_parse_min_similarity_rejects_%s", (text) => {
    expect(parseMinSimilarity(text)).toBeNull();
  });

  it("test_search_body_sends_null_threshold_when_blank", () => {
    expect(searchBody({ query: "caixa", minSimilarity: " ", rerank: "default" })).toEqual({
      query: "caixa",
      limit: 10,
      min_similarity: null,
      rerank: null,
      level: "product_dev",
    });
    expect(
      searchBody({ query: "caixa", minSimilarity: "0,6", rerank: "default" }).min_similarity,
    ).toBe(0.6);
  });

  it.each([
    ["default", null],
    ["on", true],
    ["off", false],
  ] as const)("test_search_body_maps_rerank_%s", (rerank, sent) => {
    expect(searchBody({ query: "caixa", minSimilarity: "", rerank }).rerank).toBe(sent);
  });

  it("test_search_form_schema_validates_query_and_threshold", () => {
    const result = searchFormSchema(t).safeParse({
      query: "  ",
      minSimilarity: "2",
      rerank: "default",
    });

    expect(result.error?.issues.map((issue) => issue.message)).toEqual([
      "Digite o que deseja buscar.",
      "Informe um número de 0 a 1.",
    ]);
    expect(
      searchFormSchema(t).safeParse({ query: "x", minSimilarity: " ", rerank: "off" }).success,
    ).toBe(true);
  });

  it("test_result_location_for_files_and_commits", () => {
    expect(resultLocation(makeSearchResult())).toBe("src/caixa.py:10–24");
    expect(resultLocation(makeCommitSearchResult())).toBe("commit abcdef1");
    expect(resultLocation(makeSearchResult({ end_line: 10 }))).toBe("src/caixa.py:10");
    expect(resultLocation(makeSearchResult({ end_line: null }))).toBe("src/caixa.py:10");
    expect(resultLocation(makeSearchResult({ start_line: null, end_line: null }))).toBe(
      "src/caixa.py",
    );
    expect(resultLocation(makeSearchResult({ path: null, start_line: null }))).toBe("src/caixa.py");
  });

  it("test_result_location_of_commit_without_sha_uses_document_key", () => {
    expect(resultLocation(makeCommitSearchResult({ meta: {} }))).toBe("commit abcdef1");
  });

  it("test_result_language_reads_meta", () => {
    expect(resultLanguage(makeSearchResult())).toBe("python");
    expect(resultLanguage(makeSearchResult({ meta: { language: "" } }))).toBeUndefined();
    expect(resultLanguage(makeSearchResult({ meta: { language: 3 } }))).toBeUndefined();
  });

  it("test_format_score_in_locale_with_dash_for_null", () => {
    expect(formatScore(0.5234, 2, "pt-BR")).toBe("0,52");
    expect(formatScore(null, 2, "pt-BR")).toBe("—");
  });
});
