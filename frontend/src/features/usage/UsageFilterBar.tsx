import { useId } from "react";
import { useTranslation } from "react-i18next";

import { FilterSelect } from "@/components/FilterSelect";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { RESPONSE_LEVELS } from "@/lib/api/levels";
import type { UsageGroup } from "@/lib/api/usage";
import { levelLabel, parseLevel } from "@/lib/responseLevels";
import {
  acceptsChatFilters,
  type DayRange,
  USAGE_GROUPS,
  USAGE_PRESETS,
  type UsagePreset,
  type UsageSearch,
} from "@/lib/usagePeriod";

/** Value of the "no filter" item: Radix Select items cannot have an empty value. */
const ALL = "all";

/** A product the filter offers. */
export interface ProductChoice {
  id: string;
  name: string;
}

interface UsageFilterBarProps {
  search: UsageSearch;
  /** Days of the period on screen, to start a custom period from them. */
  days: Partial<DayRange>;
  /** The workspace's products, for the product filter. */
  products: readonly ProductChoice[];
  onChange: (search: UsageSearch) => void;
}

/**
 * Period (ready-made or custom days), grouping, product and level of the report; each change
 * applies now. Product and level restrict the chat, so they are off when grouping by source or
 * collection (embeddings only), with the reason next to them.
 */
export function UsageFilterBar({ search, days, products, onChange }: UsageFilterBarProps) {
  const { t } = useTranslation();
  const periodId = useId();
  const fromId = useId();
  const toId = useId();
  const groupId = useId();
  const productId = useId();
  const levelId = useId();
  const chatOnlyId = useId();
  const chatFilters = acceptsChatFilters(search.group);
  // A shared link may name a product no longer listed: keep it selectable, by id.
  const productOptions =
    search.product === undefined || products.some(({ id }) => id === search.product)
      ? products
      : [...products, { id: search.product, name: search.product }];

  return (
    <fieldset className="flex flex-wrap items-end gap-4">
      <legend className="sr-only">{t("usage.filters.label")}</legend>
      <div className="flex flex-col gap-2">
        <Label htmlFor={periodId}>{t("usage.filters.period")}</Label>
        <FilterSelect
          id={periodId}
          className="w-full sm:w-48"
          value={search.preset}
          options={USAGE_PRESETS.map((preset) => ({
            value: preset,
            label: t(`usage.presets.${preset}`),
          }))}
          onValueChange={(value) => {
            // The select only offers the presets above.
            const preset = value as UsagePreset;
            onChange(
              preset === "custom"
                ? { ...search, preset, from: days.from, to: days.to }
                : { ...search, preset, from: undefined, to: undefined },
            );
          }}
        />
      </div>
      {search.preset === "custom" && (
        <>
          <div className="flex flex-col gap-2">
            <Label htmlFor={fromId}>{t("usage.filters.from")}</Label>
            <Input
              id={fromId}
              type="date"
              className="w-full sm:w-44"
              value={search.from ?? ""}
              max={search.to}
              onChange={(event) => {
                onChange({ ...search, from: event.target.value || undefined });
              }}
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor={toId}>{t("usage.filters.to")}</Label>
            <Input
              id={toId}
              type="date"
              className="w-full sm:w-44"
              value={search.to ?? ""}
              min={search.from}
              onChange={(event) => {
                onChange({ ...search, to: event.target.value || undefined });
              }}
            />
          </div>
        </>
      )}
      <div className="flex flex-col gap-2">
        <Label htmlFor={groupId}>{t("usage.filters.group")}</Label>
        <FilterSelect
          id={groupId}
          className="w-full sm:w-48"
          value={search.group}
          options={USAGE_GROUPS.map((group) => ({
            value: group,
            label: t(`usage.groups.${group}`),
          }))}
          onValueChange={(value) => {
            // The select only offers the groupings above. The URL drops the product and level of a
            // grouping that refuses them.
            onChange({ ...search, group: value as UsageGroup });
          }}
        />
      </div>
      <div className="flex flex-col gap-2">
        <Label htmlFor={productId}>{t("usage.filters.product")}</Label>
        <FilterSelect
          id={productId}
          className="w-full sm:w-48"
          disabled={!chatFilters}
          describedBy={chatFilters ? undefined : chatOnlyId}
          value={search.product ?? ALL}
          options={[
            { value: ALL, label: t("usage.filters.allProducts") },
            ...productOptions.map(({ id, name }) => ({ value: id, label: name })),
          ]}
          onValueChange={(value) => {
            onChange({ ...search, product: value === ALL ? undefined : value });
          }}
        />
      </div>
      <div className="flex flex-col gap-2">
        <Label htmlFor={levelId}>{t("usage.filters.level")}</Label>
        <FilterSelect
          id={levelId}
          className="w-full sm:w-56"
          disabled={!chatFilters}
          describedBy={chatFilters ? undefined : chatOnlyId}
          value={search.level ?? ALL}
          options={[
            { value: ALL, label: t("usage.filters.allLevels") },
            ...RESPONSE_LEVELS.map((level) => ({ value: level, label: levelLabel(level, t) })),
          ]}
          onValueChange={(value) => {
            onChange({ ...search, level: parseLevel(value) });
          }}
        />
      </div>
      {!chatFilters && (
        <p id={chatOnlyId} className="text-muted-foreground basis-full text-xs">
          {t("usage.filters.chatOnly")}
        </p>
      )}
    </fieldset>
  );
}
