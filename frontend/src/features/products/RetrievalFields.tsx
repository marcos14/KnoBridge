import { useId } from "react";
import type { Control } from "react-hook-form";
import { useTranslation } from "react-i18next";

import { TextField } from "@/components/TextField";
import { Checkbox } from "@/components/ui/checkbox";
import { FormControl, FormDescription, FormField, FormItem, FormLabel } from "@/components/ui/form";
import type { Product } from "@/lib/api/products";
import { formatDecimal } from "@/lib/numberFormat";

import type { ProductFormValues } from "./productForm";

interface RetrievalFieldsProps {
  control: Control<ProductFormValues>;
  /** The product being edited: its saved floors per embedding model are shown. */
  product?: Product;
  /** Whether the instance has a reranker; `undefined` while nobody knows (no product loaded). */
  rerankAvailable: boolean | undefined;
}

/**
 * How the product searches: the similarity floor (blank is the default of each collection's
 * embedding model, with the floors in use when editing) and "Reordenar trechos" (the reranker).
 */
export function RetrievalFields({ control, product, rerankAvailable }: RetrievalFieldsProps) {
  const { t, i18n } = useTranslation();
  const effectiveId = useId();
  const effective = product?.effective_min_similarity ?? [];
  return (
    <>
      <div className="flex flex-col gap-2">
        <TextField
          control={control}
          name="minSimilarity"
          inputMode="decimal"
          label={t("products.form.minSimilarity")}
          description={t("products.form.minSimilarityHint")}
        />
        {effective.length > 0 && (
          <div className="flex flex-col gap-1 text-sm">
            <p id={effectiveId} className="text-muted-foreground">
              {t("products.form.effectiveTitle")}
            </p>
            <ul aria-labelledby={effectiveId} className="flex flex-col gap-0.5">
              {effective.map((item) => (
                <li key={item.embedding_model}>
                  {t("products.form.effectiveItem", {
                    model: item.embedding_model,
                    value: formatDecimal(item.value, 2, i18n.language),
                    source: t(`products.form.effectiveSources.${item.source}`),
                  })}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
      <FormField
        control={control}
        name="rerank"
        render={({ field }) => (
          <FormItem className="flex flex-row items-start gap-3">
            <FormControl>
              <Checkbox
                checked={field.value}
                disabled={rerankAvailable === false}
                onCheckedChange={(checked) => {
                  field.onChange(checked === true);
                }}
              />
            </FormControl>
            <div className="flex flex-col gap-1">
              <FormLabel>{t("products.form.rerank")}</FormLabel>
              <FormDescription>
                {rerankAvailable === false
                  ? t("products.form.rerankUnavailable")
                  : t("products.form.rerankHint")}
              </FormDescription>
            </div>
          </FormItem>
        )}
      />
    </>
  );
}
