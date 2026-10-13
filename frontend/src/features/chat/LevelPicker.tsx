import { useId } from "react";
import { useTranslation } from "react-i18next";

import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { RESPONSE_LEVELS, type ResponseLevel } from "@/lib/api/levels";
import { isLevelAbove, levelAudience, levelLabel } from "@/lib/responseLevels";
import { cn } from "@/lib/utils";

interface LevelPickerProps {
  /** The member's maximum level in the chosen product (`my_max_level`). */
  maxLevel: ResponseLevel;
  value: ResponseLevel;
  onChange: (level: ResponseLevel) => void;
}

/**
 * The response level of a new conversation: the three levels in order, each with who it is for;
 * the ones above the member's maximum in the product stay visible but disabled, saying why.
 */
export function LevelPicker({ maxLevel, value, onChange }: LevelPickerProps) {
  const { t } = useTranslation();
  const labelId = useId();

  return (
    <fieldset className="flex flex-col gap-2">
      <legend id={labelId} className="text-sm font-medium">
        {t("chat.levels.label")}
      </legend>
      <RadioGroup
        aria-labelledby={labelId}
        value={value}
        onValueChange={(next) => {
          // Radix only hands back the `value` of one of the items below.
          onChange(next as ResponseLevel);
        }}
        className="grid gap-3 sm:grid-cols-3"
      >
        {RESPONSE_LEVELS.map((level) => {
          const unavailable = isLevelAbove(level, maxLevel);
          const id = `${labelId}-${level}`;
          return (
            <div key={level} className="flex items-start gap-2">
              <RadioGroupItem
                id={id}
                value={level}
                disabled={unavailable}
                aria-describedby={`${id}-hint`}
                className="mt-0.5"
              />
              <div className="flex flex-col gap-0.5">
                <Label htmlFor={id} className={cn(unavailable && "text-muted-foreground")}>
                  {levelLabel(level, t)}
                </Label>
                <p id={`${id}-hint`} className="text-muted-foreground text-xs">
                  {unavailable
                    ? t("chat.levels.unavailable", { max: levelLabel(maxLevel, t) })
                    : levelAudience(level, t)}
                </p>
              </div>
            </div>
          );
        })}
      </RadioGroup>
      <p className="text-muted-foreground text-xs">{t("chat.levels.hint")}</p>
    </fieldset>
  );
}
