import type { TFunction } from "i18next";
import { z } from "zod";

import type { SearchRequest, SearchResult } from "@/lib/api/collections";

/** Limits and defaults of the search route (`api/search.py`, `retrieval/search.py`). */
export const QUERY_MAX_LENGTH = 2000;
export const SEARCH_LIMIT = 10;
export const DEFAULT_MIN_SIMILARITY = 0.35;
const SHORT_SHA_LENGTH = 7;

/**
 * Minimum similarity typed as text, with a comma or a dot ("0,45"): `null` when it is not a plain
 * number from 0 to 1. Blank means "the API default" and is handled by the caller.
 */
export function parseMinSimilarity(text: string): number | null {
  const normalized = text.trim().replace(",", ".");
  if (!/^\d+(\.\d+)?$/.test(normalized)) {
    return null;
  }
  const value = Number(normalized);
  return value <= 1 ? value : null;
}

export interface SearchFormValues {
  query: string;
  minSimilarity: string;
}

export function searchFormSchema(t: TFunction) {
  return z.object({
    query: z
      .string()
      .trim()
      .min(1, { error: t("collections.search.validation.queryRequired") })
      .max(QUERY_MAX_LENGTH, { error: t("auth.validation.tooLong", { max: QUERY_MAX_LENGTH }) }),
    minSimilarity: z
      .string()
      .refine((value) => value.trim() === "" || parseMinSimilarity(value) !== null, {
        error: t("collections.search.validation.minSimilarityInvalid"),
      }),
  });
}

/** Threshold of the search: the typed one or, left blank, the API default. */
export function effectiveMinSimilarity(values: SearchFormValues): number {
  return parseMinSimilarity(values.minSimilarity) ?? DEFAULT_MIN_SIMILARITY;
}

/** Body of the search, with the threshold always explicit (the screen shows which it used). */
export function searchBody(values: SearchFormValues): SearchRequest {
  return {
    query: values.query,
    limit: SEARCH_LIMIT,
    min_similarity: effectiveMinSimilarity(values),
  };
}

function metaString(result: SearchResult, key: string): string | undefined {
  const value = result.meta[key];
  return typeof value === "string" && value !== "" ? value : undefined;
}

/** Programming language of a code chunk (`meta.language`), when the indexer knew it. */
export function resultLanguage(result: SearchResult): string | undefined {
  return metaString(result, "language");
}

/**
 * Where the chunk comes from, as a citation shows it: `path:start–end` (or `path:line`, or the path
 * alone for converted documents), `commit <sha>` for a commit, or the document title when there is
 * no path.
 */
export function resultLocation(result: SearchResult): string {
  if (result.document.kind === "commit") {
    const sha = metaString(result, "sha") ?? result.document.key;
    return `commit ${sha.slice(0, SHORT_SHA_LENGTH)}`;
  }
  const path = result.path ?? result.document.title;
  const { start_line: start, end_line: end } = result;
  if (start === null) {
    return path;
  }
  return end === null || end === start
    ? `${path}:${String(start)}`
    : `${path}:${String(start)}–${String(end)}`;
}

/**
 * A score for reading, in the interface language: `digits` decimal places, `—` when the arm did
 * not find the chunk (`null`).
 */
export function formatScore(value: number | null, digits: number, locale: string): string {
  if (value === null) {
    return "—";
  }
  return new Intl.NumberFormat(locale, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value);
}
