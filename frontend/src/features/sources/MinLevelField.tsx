import { useId } from "react";
import { type UseFormReturn, useWatch } from "react-hook-form";
import { useTranslation } from "react-i18next";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { RESPONSE_LEVELS, type ResponseLevel } from "@/lib/api/levels";
import type { Source } from "@/lib/api/sources";
import { defaultSourceMinLevel, isLevelAbove } from "@/lib/responseLevels";

import { formatCount } from "./format";
import { formMinLevel, type SourceFormValues } from "./sourceForm";

interface MinLevelFieldProps {
  form: UseFormReturn<SourceFormValues>;
  /** The stored source when editing: its level and documents decide the warning. */
  source?: Source;
  /** Owners and admins; editors see the level but cannot change it (403 on the server). */
  canChange: boolean;
}

/**
 * The minimum response level of the source: only answers at this level or above use it. A new
 * source follows its kind's default until someone picks a level; changing the level of a source
 * with documents warns which answers stop (or start) using them, at once and without reindexing.
 */
export function MinLevelField({ form, source, canChange }: MinLevelFieldProps) {
  const { t, i18n } = useTranslation();
  const id = useId();
  const hintId = useId();
  const [kind, minLevel] = useWatch({ control: form.control, name: ["kind", "minLevel"] });
  const level = formMinLevel({ kind, minLevel });
  const kindDefault = defaultSourceMinLevel(kind);
  const levelName = (value: ResponseLevel) => t(`workspaceSettings.levels.names.${value}`);
  const changed = source !== undefined && source.document_count > 0 && level !== source.min_level;

  return (
    <div className="flex flex-col gap-2">
      <label htmlFor={id} className="text-sm font-medium">
        {t("sources.form.minLevel")}
      </label>
      <Select
        value={level}
        disabled={!canChange}
        onValueChange={(value) => {
          // Radix only hands back the `value` of one of the items below, all response levels.
          form.setValue("minLevel", value as ResponseLevel, { shouldDirty: true });
        }}
      >
        <SelectTrigger id={id} aria-describedby={hintId} className="w-full">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {RESPONSE_LEVELS.map((item) => (
            <SelectItem key={item} value={item}>
              {item === kindDefault
                ? t("sources.form.minLevelDefault", { level: levelName(item) })
                : levelName(item)}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <p id={hintId} className="text-muted-foreground text-sm">
        {t("sources.form.minLevelHint", { level: levelName(kindDefault) })}{" "}
        {!canChange && t("sources.form.minLevelAdminsOnly")}
      </p>
      {changed && (
        <p role="note" className="text-sm font-medium">
          {t(
            isLevelAbove(level, source.min_level)
              ? "sources.form.minLevelRaised"
              : "sources.form.minLevelLowered",
            {
              count: source.document_count,
              formatted: formatCount(source.document_count, i18n.language),
              level: levelName(level),
            },
          )}
        </p>
      )}
    </div>
  );
}
