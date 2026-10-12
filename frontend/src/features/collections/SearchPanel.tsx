import { zodResolver } from "@hookform/resolvers/zod";
import { useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";

import { FormAlert } from "@/components/FormAlert";
import { TextField } from "@/components/TextField";
import { Button } from "@/components/ui/button";
import { Form } from "@/components/ui/form";
import { translateApiError } from "@/i18n/apiErrors";
import { type SearchResult, useSearchCollection } from "@/lib/api/collections";

import {
  DEFAULT_MIN_SIMILARITY,
  effectiveMinSimilarity,
  formatScore,
  resultLanguage,
  resultLocation,
  searchBody,
  searchFormSchema,
  type SearchFormValues,
} from "./searchResult";

/** Decimal places of each score: RRF sums are small, similarities and ranks less so. */
const FUSED_DIGITS = 4;
const VECTOR_DIGITS = 2;
const FTS_DIGITS = 3;

interface SearchPanelProps {
  workspaceId: string;
  collectionId: string;
}

/**
 * "Testar busca" (any member): a query, an optional minimum similarity and the chunks the hybrid
 * search returns, best first, with their scores, where they come from and the snippet.
 */
export function SearchPanel({ workspaceId, collectionId }: SearchPanelProps) {
  const { t, i18n } = useTranslation();
  const search = useSearchCollection(workspaceId, collectionId);
  const [threshold, setThreshold] = useState(DEFAULT_MIN_SIMILARITY);
  const schema = useMemo(() => searchFormSchema(t), [t]);
  const form = useForm<SearchFormValues>({
    resolver: zodResolver(schema),
    defaultValues: { query: "", minSimilarity: "" },
  });
  const locale = i18n.language;

  function onSubmit(values: SearchFormValues) {
    setThreshold(effectiveMinSimilarity(values));
    search.mutate(searchBody(values));
  }

  return (
    <section aria-labelledby="collection-search" className="flex flex-col gap-4">
      <div className="flex flex-col gap-1">
        <h2 id="collection-search" className="text-lg font-semibold">
          {t("collections.search.title")}
        </h2>
        <p className="text-muted-foreground text-sm">{t("collections.search.description")}</p>
      </div>
      <Form {...form}>
        <form
          noValidate
          className="flex flex-col gap-4"
          onSubmit={(event) => void form.handleSubmit(onSubmit)(event)}
        >
          <TextField
            control={form.control}
            name="query"
            rows={2}
            label={t("collections.search.query")}
          />
          <div className="max-w-xs">
            <TextField
              control={form.control}
              name="minSimilarity"
              inputMode="decimal"
              label={t("collections.search.minSimilarity")}
              description={t("collections.search.minSimilarityHint", {
                default: formatScore(DEFAULT_MIN_SIMILARITY, 2, locale),
              })}
            />
          </div>
          <div>
            <Button type="submit" disabled={search.isPending}>
              {search.isPending
                ? t("collections.search.searching")
                : t("collections.search.submit")}
            </Button>
          </div>
        </form>
      </Form>
      {search.isError && <FormAlert message={translateApiError(search.error, t)} />}
      {search.isSuccess &&
        (search.data.length === 0 ? (
          <p
            role="status"
            className="text-muted-foreground rounded-md border border-dashed p-4 text-sm"
          >
            {t("collections.search.empty", { threshold: formatScore(threshold, 2, locale) })}
          </p>
        ) : (
          <div className="flex flex-col gap-3">
            <p role="status" className="text-sm">
              {t("collections.search.resultCount", { count: search.data.length })}
            </p>
            <ol aria-label={t("collections.search.resultsLabel")} className="flex flex-col gap-3">
              {search.data.map((result) => (
                <SearchResultItem key={result.chunk_id} result={result} locale={locale} />
              ))}
            </ol>
          </div>
        ))}
    </section>
  );
}

function SearchResultItem({ result, locale }: { result: SearchResult; locale: string }) {
  const { t } = useTranslation();
  const location = resultLocation(result);
  const language = resultLanguage(result);
  const isCommit = result.document.kind === "commit";

  return (
    <li className="flex flex-col gap-2 rounded-md border p-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div className="flex flex-col">
          <span className="font-mono text-sm font-medium">{location}</span>
          {isCommit && <span className="text-sm">{result.document.title}</span>}
        </div>
        <span className="text-muted-foreground text-xs">
          {t("collections.search.scores", {
            fused: formatScore(result.scores.fused, FUSED_DIGITS, locale),
            vector: formatScore(result.scores.vector, VECTOR_DIGITS, locale),
            fts: formatScore(result.scores.fts, FTS_DIGITS, locale),
          })}
        </span>
      </div>
      {(result.symbol !== null || language !== undefined) && (
        <p className="text-muted-foreground flex flex-wrap gap-3 text-xs">
          {result.symbol !== null && (
            <span>{t("collections.search.symbol", { symbol: result.symbol })}</span>
          )}
          {language !== undefined && <span>{t("collections.search.language", { language })}</span>}
        </p>
      )}
      <pre className="bg-muted overflow-x-auto rounded-md p-3 text-xs">
        <code className={language === undefined ? undefined : `language-${language}`}>
          {result.snippet}
        </code>
      </pre>
    </li>
  );
}
