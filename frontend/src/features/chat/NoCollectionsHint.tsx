import { Info } from "lucide-react";
import { useTranslation } from "react-i18next";

import type { Product } from "@/lib/api/products";

/** Discreet note above the composer when the product has no collection to answer from. */
export function NoCollectionsHint({ product }: { product: Product | undefined }) {
  const { t } = useTranslation();
  if (product === undefined || product.collection_ids.length > 0) {
    return null;
  }
  return (
    <p className="text-muted-foreground flex items-center gap-1.5 text-xs">
      <Info aria-hidden="true" className="size-3.5 shrink-0" />
      {t("chat.products.noCollections")}
    </p>
  );
}
