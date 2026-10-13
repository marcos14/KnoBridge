import { useTranslation } from "react-i18next";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { RESPONSE_LEVELS, type ResponseLevel } from "@/lib/api/levels";
import { levelLabel } from "@/lib/responseLevels";

/** The value of the "default of the role" option (no stored level). */
export const DEFAULT_LEVEL = "default";

export type LevelChoice = ResponseLevel | typeof DEFAULT_LEVEL;

interface MemberLevelSelectProps {
  value: LevelChoice;
  /** The level the default stands for (by the member's or the invitation's role). */
  defaultLevel: ResponseLevel;
  onChange: (value: LevelChoice) => void;
  label: string;
  /** Text of the default option; `defaultLevel` is interpolated as `level`. */
  defaultLabel: "members.levels.default" | "members.invite.levelDefault";
  disabled?: boolean;
}

/**
 * Maximum level picker of a member (or an invitation) in one product: the default of the role,
 * shown with the level it stands for, or one of the three levels.
 */
export function MemberLevelSelect({
  value,
  defaultLevel,
  onChange,
  label,
  defaultLabel,
  disabled,
}: MemberLevelSelectProps) {
  const { t } = useTranslation();
  const levelName = (level: ResponseLevel) => levelLabel(level, t);

  return (
    <Select
      value={value}
      disabled={disabled}
      onValueChange={(next) => {
        // Radix only hands back the `value` of one of the items below.
        onChange(next as LevelChoice);
      }}
    >
      <SelectTrigger aria-label={label} className="w-full min-w-44">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={DEFAULT_LEVEL}>
          {t(defaultLabel, { level: levelName(defaultLevel) })}
        </SelectItem>
        {RESPONSE_LEVELS.map((level) => (
          <SelectItem key={level} value={level}>
            {levelName(level)}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
