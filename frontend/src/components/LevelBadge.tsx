import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import type { ResponseLevel } from "@/lib/api/levels";
import { levelLabel } from "@/lib/responseLevels";

/**
 * Seal of a response level ("Nível: Suporte"): of a conversation in the chat and in the
 * workspace's conversations, and of an API key's maximum.
 */
export function LevelBadge({ level }: { level: ResponseLevel }) {
  const { t } = useTranslation();
  return (
    <Badge variant="outline" className="font-normal">
      {t("chat.levels.badge", { level: levelLabel(level, t) })}
    </Badge>
  );
}
