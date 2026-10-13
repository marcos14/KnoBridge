import { useId } from "react";
import { useTranslation } from "react-i18next";

import { FilterSelect } from "@/components/FilterSelect";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { UsageGroup } from "@/lib/api/usage";
import {
  type DayRange,
  USAGE_GROUPS,
  USAGE_PRESETS,
  type UsagePreset,
  type UsageSearch,
} from "@/lib/usagePeriod";

interface UsageFilterBarProps {
  search: UsageSearch;
  /** Days of the period on screen, to start a custom period from them. */
  days: Partial<DayRange>;
  onChange: (search: UsageSearch) => void;
}

/** Period (ready-made or custom days) and grouping of the report; each change applies now. */
export function UsageFilterBar({ search, days, onChange }: UsageFilterBarProps) {
  const { t } = useTranslation();
  const periodId = useId();
  const fromId = useId();
  const toId = useId();
  const groupId = useId();

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
                ? { preset, group: search.group, from: days.from, to: days.to }
                : { preset, group: search.group },
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
            // The select only offers the groupings above.
            onChange({ ...search, group: value as UsageGroup });
          }}
        />
      </div>
    </fieldset>
  );
}
