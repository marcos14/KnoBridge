import { useId } from "react";
import { useTranslation } from "react-i18next";

import { FilterSelect } from "@/components/FilterSelect";
import { Label } from "@/components/ui/label";
import type { ConversationListFilters } from "@/lib/api/conversations";
import { RESPONSE_LEVELS } from "@/lib/api/levels";
import { useProducts } from "@/lib/api/products";
import { levelLabel, parseLevel } from "@/lib/responseLevels";

/** Value of the "no filter" item: Radix Select items cannot have an empty value. */
const ALL = "all";

interface ConversationListFilterBarProps {
  workspaceId: string;
  filters: ConversationListFilters;
  onChange: (filters: ConversationListFilters) => void;
}

/** Product and level of the member's conversations; each change applies now. */
export function ConversationListFilterBar({
  workspaceId,
  filters,
  onChange,
}: ConversationListFilterBarProps) {
  const { t } = useTranslation();
  const productId = useId();
  const levelId = useId();
  // Inactive products keep their conversations, so every product the member sees is offered.
  const products = useProducts(workspaceId);

  return (
    <fieldset className="grid grid-cols-2 gap-2 md:grid-cols-1">
      <legend className="sr-only">{t("chat.list.filters")}</legend>
      <div className="flex min-w-0 flex-col gap-1">
        <Label htmlFor={productId} className="sr-only">
          {t("chat.list.product")}
        </Label>
        <FilterSelect
          id={productId}
          className="w-full"
          value={filters.productId ?? ALL}
          options={[
            { value: ALL, label: t("chat.list.allProducts") },
            ...(products.data ?? []).map(({ id, name }) => ({ value: id, label: name })),
          ]}
          onValueChange={(value) => {
            onChange({ ...filters, productId: value === ALL ? undefined : value });
          }}
        />
      </div>
      <div className="flex min-w-0 flex-col gap-1">
        <Label htmlFor={levelId} className="sr-only">
          {t("chat.list.level")}
        </Label>
        <FilterSelect
          id={levelId}
          className="w-full"
          value={filters.level ?? ALL}
          options={[
            { value: ALL, label: t("chat.list.allLevels") },
            ...RESPONSE_LEVELS.map((level) => ({ value: level, label: levelLabel(level, t) })),
          ]}
          onValueChange={(value) => {
            onChange({ ...filters, level: parseLevel(value) });
          }}
        />
      </div>
    </fieldset>
  );
}
